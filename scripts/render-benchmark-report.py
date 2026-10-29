# /// script
# requires-python = ">=3.14,<3.15"
# dependencies = ["matplotlib==3.11.2"]
# ///
"""Build standalone PNG, HTML, Markdown, CSV and ZIP benchmark reports."""

import argparse
import base64
import csv
from html import escape
import json
from pathlib import Path
import shutil
import statistics
import sys
import zipfile

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.ticker import MaxNLocator


BACKGROUND = '#0f172a'
TEXT = '#e2e8f0'
MUTED = '#94a3b8'


def summarize(data):
    assert data['status'] == 'complete', 'Only complete runs can become final reports'
    rows = []
    for scenario in data['scenarios']:
        for compiler in data['compilers']:
            records = [r for r in data['records'] if r['scenario'] == scenario['id'] and r['compiler'] == compiler['id'] and r['phase'] == 'run']
            assert len(records) == data['runs'] and all(r['exitCode'] == 0 and not r['timedOut'] for r in records)
            times = [r['wallMs'] / 1000 for r in records]
            memory = [r['peakRssBytes'] / 1024 / 1024 for r in records]
            check = [r['checkMs'] / 1000 for r in records if r.get('checkMs') is not None]
            mapper = [r['mapperWaitMs'] / 1000 for r in records if r.get('mapperWaitMs') is not None]
            rows.append({
                'scenario': scenario['id'], 'compiler': compiler['id'], 'name': compiler['name'], 'color': compiler['color'],
                'seconds': statistics.median(times), 'minSeconds': min(times), 'maxSeconds': max(times), 'samplesSeconds': times,
                'peakRssMiB': statistics.median(memory), 'minPeakRssMiB': min(memory), 'maxPeakRssMiB': max(memory), 'samplesPeakRssMiB': memory,
                'checkSeconds': statistics.median(check) if check else None,
                'mapperWaitSeconds': statistics.median(mapper) if mapper else None,
            })
        baseline = next(row for row in rows if row['scenario'] == scenario['id'] and row['compiler'] == 'vue-tsc')
        for row in rows:
            if row['scenario'] == scenario['id']:
                row['speedupVsTs6'] = baseline['seconds'] / row['seconds']
    return rows


def draw_pair(axes, scenario, rows):
    selected = [row for row in rows if row['scenario'] == scenario['id']]
    for index, (ax, field, lower, upper, title) in enumerate([
        (axes[0], 'seconds', 'minSeconds', 'maxSeconds', 'Time (seconds)'),
        (axes[1], 'peakRssMiB', 'minPeakRssMiB', 'maxPeakRssMiB', 'Peak process-tree RSS (MiB)'),
    ]):
        ax.set_facecolor(BACKGROUND)
        values = [row[field] for row in selected]
        colors = [row['color'] for row in selected]
        y = list(range(len(selected)))
        ax.barh(y, values, color=colors, height=0.57, zorder=3)
        errors = [[row[field] - row[lower] for row in selected], [row[upper] - row[field] for row in selected]]
        ax.errorbar(values, y, xerr=errors, fmt='none', color=TEXT, alpha=0.6, capsize=3, linewidth=1, zorder=4)
        ax.set_yticks(y, [row['name'] for row in selected], fontsize=9.5, color=TEXT)
        ax.invert_yaxis()
        maximum = max(row[upper] for row in selected)
        ax.set_xlim(0, maximum * (1.62 if index == 0 else 1.28))
        ax.set_title(title, loc='left', color=TEXT, fontsize=11, pad=17, weight='bold')
        ax.tick_params(axis='both', colors=MUTED, length=0)
        ax.xaxis.set_major_locator(MaxNLocator(4))
        ax.grid(axis='x', color='#334155', linewidth=0.6, alpha=0.5, zorder=0)
        for spine in ax.spines.values():
            spine.set_visible(False)
        for position, row in enumerate(selected):
            annotation = f"{row[field]:.2f}" if index == 0 else f"{row[field]:,.0f}"
            if index == 0 and row['compiler'] != 'vue-tsc':
                annotation += f"  {row['speedupVsTs6']:.2f}x"
            ax.text(row[upper] + maximum * 0.025, position, annotation, va='center', color=TEXT, fontsize=9.5)


def charts(output, data, rows):
    plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 9, 'savefig.facecolor': BACKGROUND})
    images = []
    for scenario in data['scenarios']:
        fig, axes = plt.subplots(1, 2, figsize=(11, 4.8))
        fig.patch.set_facecolor(BACKGROUND)
        fig.subplots_adjust(left=0.20, right=0.98, top=0.73, bottom=0.18, wspace=1.05)
        draw_pair(axes, scenario, rows)
        fig.text(0.04, 0.91, f"{scenario['name']}  |  {scenario['totalLines']:,} source lines", color=TEXT, fontsize=16, weight='bold')
        fig.text(0.04, 0.83, f"500 physical lines/file | median of {data['runs']} runs | lower is better", color=MUTED, fontsize=10)
        fig.text(0.04, 0.045, 'Whiskers: min-max. Time includes Vue transforms. Memory: sampled summed tree RSS, including mapper/API workers.', color=MUTED, fontsize=8)
        path = output / f"{scenario['id']}.png"
        fig.savefig(path, dpi=180)
        fig.savefig(path.with_suffix('.svg'))
        plt.close(fig)
        images.append(path)

    count = len(data['scenarios'])
    height = 4.0 * count + 1.4
    fig, axes = plt.subplots(count, 2, figsize=(11, height), squeeze=False)
    fig.patch.set_facecolor(BACKGROUND)
    fig.subplots_adjust(left=0.20, right=0.98, top=1 - 1.9 / height, bottom=0.7 / height, hspace=0.9, wspace=1.05)
    fig.text(0.04, 1 - 0.42 / height, 'Vue / TypeScript type-checking benchmark', color=TEXT, fontsize=19, weight='bold')
    fig.text(0.04, 1 - 0.80 / height, f"500 lines/file | {data['runs']} measured runs + {data['warmup']} warmup(s) per tool/scenario | lower is better", color=MUTED, fontsize=10)
    for index, scenario in enumerate(data['scenarios']):
        draw_pair(axes[index], scenario, rows)
        position = axes[index, 0].get_position()
        fig.text(0.04, position.y1 + 0.69 / height, f"{scenario['name']}  /  {scenario['totalLines']:,} lines", color=TEXT, fontsize=13, weight='bold')
    fig.text(0.04, 0.18 / height, 'Speed ratio = TS6 median time / tool median time. RSS sums may count shared pages repeatedly; whiskers show min-max.', color=MUTED, fontsize=8)
    overview = output / 'overview.png'
    fig.savefig(overview, dpi=180)
    fig.savefig(overview.with_suffix('.svg'))
    plt.close(fig)
    return images, overview


def observations(data, rows):
    largest = max(data['scenarios'], key=lambda item: item['totalLines'])
    selected = [row for row in rows if row['scenario'] == largest['id']]
    fastest = min(selected, key=lambda row: row['seconds'])
    native = next(row for row in selected if row['compiler'] == 'tsc')
    rust = next(row for row in selected if row['compiler'] == 'tsrs')
    result = [
        f"最大负载 {largest['name']} 中，{fastest['name']} 的完整耗时中位数最低，为 {fastest['seconds']:.3f} 秒，是 TS 6 基线的 {fastest['speedupVsTs6']:.2f} 倍速度。",
        f"同一负载下，TS 7.1 / 普通 tsrs 的完整耗时为 {native['seconds']:.3f} / {rust['seconds']:.3f} 秒，峰值进程树 RSS 中位数为 {native['peakRssMiB']:.1f} / {rust['peakRssMiB']:.1f} MiB。",
    ]
    if rust['mapperWaitSeconds'] is not None and rust['checkSeconds'] is not None:
        result.append(f"普通 tsrs 的 mapper 请求等待中位数为 {rust['mapperWaitSeconds']:.3f} 秒，检查阶段为 {rust['checkSeconds']:.3f} 秒；完整耗时为 {rust['seconds']:.3f} 秒。应结合这些阶段时间判断瓶颈，不能只比较 Check time。")
    by_key = {(row['scenario'], row['compiler']): row for row in rows}
    if ('ts-heavy', 'tsrs') in by_key and ('vue-heavy', 'tsrs') in by_key:
        ts, vue = by_key['ts-heavy', 'tsrs'], by_key['vue-heavy', 'tsrs']
        result.append(f"同为 40 万物理行，600 TS + 200 Vue / 200 TS + 600 Vue 的普通 tsrs 完整耗时为 {ts['seconds']:.3f} / {vue['seconds']:.3f} 秒，说明文件类型比例也会影响本次负载的成本。")
    if data['runs'] >= 2:
        overlap = 0
        for scenario in data['scenarios']:
            regular, fast = by_key[scenario['id'], 'tsrs'], by_key[scenario['id'], 'fast']
            overlap += max(regular['minSeconds'], fast['minSeconds']) <= min(regular['maxSeconds'], fast['maxSeconds'])
        result.append(f"{len(data['scenarios'])} 组负载中有 {overlap} 组的普通 tsrs 与 fast 耗时范围重叠。每项仅 {data['runs']} 个正式样本；这里报告观测值，不据此宣称小幅差距具有统计显著性。")
    return result


def md_report(data, rows):
    lines = [
        '# Vue / TypeScript benchmark 报告', '',
        f"测试完成时间：{data['completedAt']}。各场景每个文件 500 物理行，每项预热 {data['warmup']} 次、正式测量 {data['runs']} 次。", '',
        '## 测试环境与版本', '',
        f"- CPU：{data['environment']['cpu']}；可用并行度 {data['environment']['availableParallelism']}。",
        f"- 系统：{data['environment']['platform']} {data['environment']['release']} / {data['environment']['arch']}；内存 {data['environment']['totalMemoryBytes'] / 1024 ** 3:.1f} GiB。",
        f"- Node：{data['environment']['node']}；Bun：{data['environment']['bun']}；采样 Python：{data['environment']['python']}。",
        f"- vue-tsc {data['versions']['vueTsc']} + TypeScript {data['versions']['typescript6']}；原生 TypeScript {data['versions']['typescript']}。",
        f"- tsrs {data['versions']['tsrs']}；Vue mapper {data['versions']['mapper']}；Vue {data['versions']['vue']}。", '',
        '## 测量口径', '',
        '- 完整新进程墙钟时间，包含编译器、Vue 转换和 mapper/API 启动；每项顺序执行、每轮轮换工具顺序；不清空操作系统文件缓存。',
        '- 内存是每约 25 ms 在同一轮采样中累加的编译器进程树 RSS 的峰值，包含 mapper 与 API 子进程，不包含监测器和 Bun 协调器。共享页可能被多次计数，且离散采样可能漏掉非常短暂的峰值。',
        '- 图中的内存是各轮峰值的中位数；细线是最短到最长范围。它不是单进程最大 RSS、唯一物理内存、PSS 或整个系统内存。',
        f"- 所有项 strict=true、skipLibCheck=true、noEmit=true、incremental=false；Node 堆上限 {data['methodology']['nodeHeapLimitMiB']} MiB；原生 mapper workers={data['mapperWorkers']}。",
        '- TS 6 使用隔离安装的 vue-tsc/Vue language-core v3 和 strictTemplates=true；其他项使用 Vue content mapper v4，模板检查跟随 TypeScript strict。',
        '- 每组对比使用相同源文件，已验证导入闭包不会扩大场景文件数；四组工具均先通过三类预期错误检测，正式负载均检查成功。',
        '- 这是本机的合成负载结果，不是截图中的原始项目，也不能直接推断真实业务项目的加速比例。', '',
        '## 结果解读', '',
        *[f'- {item}' for item in observations(data, rows)], '',
        '## 结果', '',
        '加速比 = TS 6 基线中位耗时 / 当前工具中位耗时；大于 1 表示更快。Check 和 mapper wait 是编译器扩展诊断中的阶段时间，不能简单相加当作总时间。', '',
    ]
    for scenario in data['scenarios']:
        lines.extend([
            f"### {scenario['name']}，{scenario['totalLines']:,} 行", '',
            f"![耗时与内存]({scenario['id']}.png)", '',
            '| 工具链 | 中位耗时(s) | 耗时范围(s) | 加速比 | 峰值 RSS 中位数(MiB) | RSS 范围(MiB) | Check(s) | mapper wait(s) |',
            '|---|---:|---:|---:|---:|---:|---:|---:|',
        ])
        for row in [r for r in rows if r['scenario'] == scenario['id']]:
            check = '—' if row['checkSeconds'] is None else f"{row['checkSeconds']:.3f}"
            mapper = '—' if row['mapperWaitSeconds'] is None else f"{row['mapperWaitSeconds']:.3f}"
            lines.append(f"| {row['name']} | {row['seconds']:.3f} | {row['minSeconds']:.3f}–{row['maxSeconds']:.3f} | {row['speedupVsTs6']:.2f}× | {row['peakRssMiB']:.1f} | {row['minPeakRssMiB']:.1f}–{row['maxPeakRssMiB']:.1f} | {check} | {mapper} |")
        lines.extend(['', f"源文件 SHA-256：`{scenario['sourceSha256']}`。", ''])
    lines.extend(['## 复现与原始数据', '', '```bash', 'bun install --frozen-lockfile', 'bun run bench:setup', 'bun run generate:bench', 'bun run bench:report', '```', '',
                  '`results.json` 保留全部正式样本、预热样本、预检结果、命令、进程数和环境；`samples.csv` 可以直接导入表格。每次测量对应的 `.log` 与 `.json` 文件也随报告保留。', '',
                  '生成器版本、源码哈希和依赖版本固定后再比较；旧版三工具计时结果未混入本次报告。', ''])
    return '\n'.join(lines)


def image_data(path):
    return 'data:image/png;base64,' + base64.b64encode(path.read_bytes()).decode()


def html_report(data, rows, images, overview):
    css = '''*{box-sizing:border-box}html,body{margin:0}body{font-family:var(--font-sans,system-ui,sans-serif);color:var(--foreground,#1f2937);line-height:1.6}.report{max-width:1100px;margin:0 auto}.section{padding:16px;margin:16px 0;background:var(--card,#f4f6f8);border-radius:var(--radius,12px)}h1{font-size:24px;margin:0 0 10px}h2{font-size:19px;margin:0 0 12px}p{margin:8px 0}.muted{color:var(--muted-foreground,#667085);font-size:13px}img{display:block;max-width:100%;height:auto;border-radius:8px}.table{overflow-x:auto}table{border-collapse:collapse;width:100%;font-size:13px;font-variant-numeric:tabular-nums}th,td{padding:8px;text-align:right;border-bottom:1px solid var(--border,#d1d5db);white-space:nowrap}th:first-child,td:first-child{text-align:left}code,pre{font-family:var(--font-mono,monospace)}pre{white-space:pre-wrap;overflow-wrap:anywhere;padding:12px;background:var(--code-background,#e9edf2);border-radius:8px}a{color:var(--primary,#2563eb)}details{margin-top:12px}li{margin:4px 0}'''
    cards = []
    for scenario, image in zip(data['scenarios'], images):
        body = []
        for row in [r for r in rows if r['scenario'] == scenario['id']]:
            body.append(f"<tr><td>{escape(row['name'])}</td><td>{row['seconds']:.3f}</td><td>{row['minSeconds']:.3f}–{row['maxSeconds']:.3f}</td><td>{row['speedupVsTs6']:.2f}×</td><td>{row['peakRssMiB']:.1f}</td><td>{row['minPeakRssMiB']:.1f}–{row['maxPeakRssMiB']:.1f}</td></tr>")
        samples = [{'tool': row['name'], 'seconds': row['samplesSeconds'], 'peakRssMiB': row['samplesPeakRssMiB']} for row in rows if row['scenario'] == scenario['id']]
        cards.append(f'''<section class="section" id="{scenario['id']}"><h2>{escape(scenario['name'])} · {scenario['totalLines']:,} 行</h2><img src="{image_data(image)}" alt="{escape(scenario['name'])} 耗时和峰值 RSS"><p class="muted">每个文件 500 行；图中为正式采样中位数，误差线为最短–最长。</p><div class="table"><table><thead><tr><th>工具链</th><th>耗时(s)</th><th>耗时范围(s)</th><th>vs TS6</th><th>峰值 RSS(MiB)</th><th>RSS 范围(MiB)</th></tr></thead><tbody>{''.join(body)}</tbody></table></div><details><summary>逐轮原始样本</summary><pre>{escape(json.dumps(samples,ensure_ascii=False,indent=2))}</pre></details><p class="muted">源码 SHA-256：<code>{scenario['sourceSha256']}</code></p><a href="{image.name}" download>下载 PNG</a> · <a href="{image.with_suffix('.svg').name}" download>下载 SVG</a></section>''')
    environment = {**data['environment'], 'versions': data['versions'], 'mapperWorkers': data['mapperWorkers']}
    insights = '<section class="section"><h2>结果解读</h2><ul>' + ''.join(f'<li>{escape(item)}</li>' for item in observations(data, rows)) + '</ul></section>'
    return f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Vue / TypeScript benchmark 报告</title><style>{css}</style></head><body><main class="report"><section class="section"><h1>Vue / TypeScript benchmark 报告</h1><p>{len(data['scenarios'])} 组负载，4 组工具链。每项预热 {data['warmup']} 次，正式测量 {data['runs']} 次。</p><p class="muted">完成于 {escape(data['completedAt'])}。加速比 = TS 6 中位耗时 / 当前工具中位耗时；大于 1 表示更快。</p><p><a href="report.md">Markdown 报告</a> · <a href="samples.csv">CSV 样本</a> · <a href="results.json">原始 JSON</a> · <a href="report.zip">完整下载</a></p><ul><li>完整新进程耗时，包含 Vue 转换与 worker 启动；不清除文件缓存，工具顺序逐轮轮换。</li><li>峰值内存是每约 25 ms 在同一轮采样中累加的编译器进程树 RSS，包含 mapper/API 子进程；共享页可能重复计数，离散采样可能漏掉瞬时峰值。图中取各轮峰值的中位数。</li><li>strict=true、skipLibCheck=true、noEmit=true、incremental=false；Node 堆上限 8 GiB；mapper workers={data['mapperWorkers']}。</li><li>TS 6 基线使用隔离的 vue-tsc v3；现代工具使用 Vue content mapper v4。所有预检与负载检查均通过。</li><li>本机合成负载，不等同于参考截图或真实业务项目。</li></ul><details><summary>环境与依赖版本</summary><pre>{escape(json.dumps(environment,ensure_ascii=False,indent=2))}</pre></details></section>{insights}<img src="{image_data(overview)}" alt="全部场景总览">{''.join(cards)}<section class="section"><h2>复现</h2><pre>bun install --frozen-lockfile\nbun run bench:setup\nbun run generate:bench\nbun run bench:report</pre><p class="muted">全部预热、正式样本、命令和日志均保留在报告目录。报告是独立 HTML，图表已内嵌，离线也可查看。</p></section></main></body></html>'''


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('results')
    args = parser.parse_args()
    source = Path(args.results).resolve()
    data = json.loads(source.read_text())
    output = source.parent
    rows = summarize(data)
    images, overview = charts(output, data, rows)
    summary = {key: value for key, value in data.items() if key != 'records'}
    summary['results'] = rows
    summary['renderer'] = {'python': sys.version.split()[0], 'matplotlib': matplotlib.__version__}
    (output / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n')
    (output / 'report.md').write_text(md_report(data, rows))
    (output / 'report.html').write_text(html_report(data, rows, images, overview))
    overview_html = f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><style>html,body{{margin:0}}img{{display:block;width:100%;height:auto}}p{{font-family:var(--font-sans,system-ui);font-size:12px;line-height:1.6;color:var(--muted-foreground);margin:10px 0 0}}</style></head><body><img src="overview.png" alt="四组负载的类型检查耗时和峰值进程树 RSS 对比"><p>每项预热 {data['warmup']} 次、正式测量 {data['runs']} 次，图中为中位数，细线为最短–最长。内存包含 mapper/API 子进程，是采样 RSS 之和；共享页可能重复计数。这是本机合成负载的实测结果。</p></body></html>'''
    (output / 'overview.html').write_text(overview_html)
    with (output / 'samples.csv').open('w', newline='') as handle:
        writer = csv.writer(handle)
        writer.writerow(['scenario','compiler','phase','round','wall_seconds','peak_tree_rss_mib','check_seconds','mapper_wait_seconds','max_processes','samples','exit_code'])
        for record in data['records']:
            writer.writerow([record['scenario'],record['compiler'],record['phase'],record['round'],record['wallMs']/1000,record['peakRssBytes']/1024/1024,None if record['checkMs'] is None else record['checkMs']/1000,None if record['mapperWaitMs'] is None else record['mapperWaitMs']/1000,record['maxProcesses'],record['samples'],record['exitCode']])
    bundle = output / 'report.zip'
    with zipfile.ZipFile(bundle, 'w', zipfile.ZIP_DEFLATED) as archive:
        for file in sorted(output.iterdir()):
            if file.is_file() and file != bundle:
                archive.write(file, file.name)
    latest = output.parent / 'latest'
    if latest != output:
        shutil.rmtree(latest, ignore_errors=True)
        shutil.copytree(output, latest)
    print('报告：', output / 'report.html')
    print('总览：', output / 'overview.png')
    print('最近报告：', latest / 'report.html')


if __name__ == '__main__':
    main()
