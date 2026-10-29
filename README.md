# tsrs + Vue content mapper 示例

用 Bun 开发和打包 Vue 3 项目，用 `tsrs` 配合 `@vue/content-mapper` 检查 `.ts`、Vue `<script setup>`、模板表达式和组件 props。类型检查不依赖 `vue-tsc`，Vite 负责开发和产物打包。

## 运行

需要 Bun 和 Node.js；mapper 会按官方协议启动 Node 子进程，因此仍需要 Node `20.19+` 或 `22.12+`。本示例使用固定版本和 `bun.lock`，安装的是发布的原生二进制，不需要 Rust 或源码构建。

```bash
cd ~/code/tsrs-vue-example
bun install --frozen-lockfile
bun dev
```

浏览器访问终端中显示的地址，默认是 `http://localhost:5173`。示例中的计数器展示了类型化 `defineProps`、`defineModel<number>` 和 `defineEmits`，以及父子组件之间的类型检查。

```bash
bun run typecheck        # tsrs 普通模式
bun run typecheck:fast   # tsrs --fast
bun run typecheck:tsc    # 官方 TypeScript 7.1 + 相同 mapper，对照使用
bun run typecheck:watch  # 持续检查，Ctrl+C 结束
bun run build           # 先通过 tsrs 检查，再由 Vite 输出 dist/
bun run preview         # 本地预览 dist/
```

开发时可以在两个终端分别运行 `bun dev` 和 `bun run typecheck:watch`。Vite 默认只转换和打包 TypeScript；类型错误由独立检查命令报告，生产构建已串联检查。

## 600 TS + 600 Vue 耗时测试

项目已生成 **600 个 `.ts` 和 600 个 `.vue` 文件，每个文件严格 500 行，合计 600,000 行**：

```text
benchmark/generated/models/entity-0000.ts       # 共 600 个 TS 模型
benchmark/generated/components/Component0000.vue # 共 600 个 Vue 组件
benchmark/generated/manifest.json              # 文件数、行数、大小
```

TS 文件包含跨模块类型引用、映射类型、泛型投影、模型工厂和字段更新函数；Vue 文件包含脚本计算属性、TS 模型引用、模板表达式、类型化 props / model / emit 和组件间引用。500 行按物理行计算，包含正常空行；Vue 的 script、template 和 style 都计算在内。

```bash
bun run check:bench     # 逐文件验证 600 + 600、每个恰好 500 行
bun run generate:bench  # 重新生成并验证；覆盖 benchmark/generated/ 中的生成内容
bun run bench:quick     # 每个检查器各跑一次，快速查看耗时
bun run bench           # 每项预热 1 次，再计时 3 次，输出中位数 / 最短 / 最长
```

`bench` 对比 tsrs 普通模式、`tsrs --fast` 和官方 TypeScript 7.1，三者使用相同的 Vue mapper、严格检查配置和固定 worker 数，并且顺序执行。每轮轮换执行顺序，预热不计入统计。

```bash
bun run bench --runs 5 --warmup 1 # 自定义采样次数
bun run bench --only tsrs        # 仅测普通 tsrs
bun run bench --only fast        # 仅测 tsrs --fast
bun run bench --only tsc         # 仅测官方 TS 7.1
```

结果写入 `benchmark/results/latest.json`，每次运行还会创建带时间戳的目录，保留全部采样、环境版本和各次 `--extendedDiagnostics` 日志。计时是新编译器进程的完整墙钟时间，包含 mapper 和 worker 启动；禁用增量检查，不清除操作系统文件缓存。默认 mapper worker 数为 CPU 可用并行度与 4 的较小值，也可通过 `VUE_CONTENT_MAPPER_WORKERS` 调整，所有对照项使用同一个值。

日志中的 `Check time` 和 `Content mapper request wait time` 可以分别观察检查阶段和 mapper 等待时间。Vue 文件较多时，总耗时可能主要花在 SFC 转换上；普通模式与 `--fast` 的完整耗时差距也可能小于它们检查阶段的差距。

`tsconfig.benchmark.json` 只检查这 1,200 个负载文件。现有 `bun run typecheck` / `typecheck:fast` / `typecheck:tsc` 也已包含该目录，另外还会检查原示例和 Vite 配置。`bun run test` 的三个故意错误示例继续单独检查，不需要重复扫描大负载。

浏览器仍显示原来的计数器；生成组件没有加入页面运行时导入，便于单独观察类型检查耗时。`bun run build` 会检查全部源文件，然后只打包页面实际引用的模块。这是合成负载，不代表截图或其他真实项目的加速比例。

## 四种工具链的图表报告

`bench:report` 在同一批生成文件上比较以下四项：

| 工具链 | 固定版本 |
|---|---|
| vue-tsc + TS 6 | vue-tsc 3.3.13 / TypeScript 6.0.3 |
| TS 7.1 + Vue mapper | TypeScript 7.1.0-beta / mapper 4.0.0-alpha.0 |
| tsrs + Vue mapper | tsrs 0.20.1-ts7.1.0-beta / 同一 mapper |
| tsrs --fast + mapper | 同上，增加 `--fast` |

TS 6 基线安装在 `benchmark/toolchains/vue-tsc/`，有独立的 lockfile，避免 vue-tsc 误用根目录的 TS 7 原生 API。基线使用 Vue language-core v3 的 `strictTemplates`，现代三项使用 mapper v4 与 TypeScript `strict`。这是完整工具链的比较，各版模板转换实现不同。

| 场景 ID | TS 文件 | Vue 文件 | 总物理行数 |
|---|---:|---:|---:|
| small-balanced | 100 | 100 | 100,000 |
| ts-heavy | 600 | 200 | 400,000 |
| vue-heavy | 200 | 600 | 400,000 |
| large-balanced | 600 | 600 | 600,000 |

各场景取生成文件的前缀，仍然每文件 500 行。模型只引用前一个模型，Vue 只引用前 100 个模型与较低编号组件，脚本会校验所有相对导入都在场景内，防止较小负载因间接引用变大。四组工具先检查三个故意错误的 fixture，再运行正式负载。

完整报告需要 **Linux / WSL 的 `/proc`**、Python 3、Bun、Node 和 [uv](https://docs.astral.sh/uv/)。采样器只使用 Python 标准库；绘图通过 uv 使用 Python 3.14 和固定版本 Matplotlib 的预编译包，不从源码构建。

```bash
bun install --frozen-lockfile
bun run bench:setup          # 安装隔离的 vue-tsc + TS 6
bun run check:bench          # 确认 600 TS + 600 Vue，每文件 500 行
bun run bench:report         # 四场景 × 四工具 × (1 次预热 + 3 次正式) = 64 次
```

测量会顺序执行，正式轮次轮换工具顺序。完整耗时包括编译器、Vue 转换和 mapper/API 启动；不清除系统文件缓存。所有项关闭增量和 emit，启用严格检查、跳过依赖声明检查，Node 堆上限统一为 8 GiB，现代工具统一 mapper worker 数（默认 4）。测量期间应避免同时运行其他重负载。

内存按 **每约 25 ms 在同一轮采样中累加的编译器进程树 RSS 的峰值**统计，包含 mapper/API 子进程，排除 Python 监测器和 Bun 协调器。共享页可能重复计数，短暂峰值也可能落在两次采样之间；它不是唯一物理内存或 PSS。报告取各轮耗时与各轮峰值 RSS 的中位数，图中细线显示最小到最大范围，保留全部单次样本。

报告保存到 `benchmark/reports/<时间戳>/`，最新一份复制到 `benchmark/reports/latest/`：

生成后可直接打开 [最新完整报告](benchmark/reports/latest/report.html)、[Markdown 报告](benchmark/reports/latest/report.md) 或 [总览图片](benchmark/reports/latest/overview.png)。

- `report.html`：图表已内嵌，可离线打开的完整报告。
- `report.md`、`overview.png`、各场景 PNG / SVG：便于阅读、分享和引用。
- `results.json`、`summary.json`、`samples.csv`：原始测量、汇总结果和表格样本。
- 每次编译的 `.log` / `.json`：诊断、命令与进程统计；`report.zip` 打包报告和原始数据。

```bash
# 指定场景、采样次数；快速命令的单次结果仅用于检查流程
bun run bench:report --scenarios ts-heavy,vue-heavy --runs 5 --warmup 1
bun run bench:report:quick

# 中断后恢复；场景、次数、依赖、源码和 worker 数必须与原运行一致
bun run bench:report --resume benchmark/reports/<时间戳>

# 用已完成的原始结果重新绘图，不重跑编译器
bun run bench:render benchmark/reports/<时间戳>/results.json
```

每完成一次测量就写入 checkpoint。若使用了自定义场景或采样次数，恢复时也要传入原参数。报告显示相对 TS 6 基线的加速比；合成负载与参考截图的源码、硬件不同，结果不能直接互相替代。旧 `bench` 的三工具计时结果不会混入这套报告。

## 关键配置

安装以下相互兼容的版本：

```bash
bun add -d --exact tsrs@0.20.1-ts7.1.0-beta \
  @vue/content-mapper@4.0.0-alpha.0 typescript@7.1.0-beta
```

`typescript` 在这里同时满足 mapper 的 `>=7.1.0-beta` peer dependency，并提供 mapper 使用的 TypeScript API。它与 `tsrs` 一起安装；默认的 `typecheck` 命令使用 tsrs。

在 `tsconfig.json` 的**顶层**注册 mapper，并把 `.vue` 纳入 `include`：

```json
{
  "compilerOptions": {
    "strict": true,
    "noEmit": true,
    "module": "ESNext",
    "moduleResolution": "Bundler"
  },
  "contentMappers": [
    {
      "package": "@vue/content-mapper",
      "extensions": [".vue"]
    }
  ],
  "include": ["src/**/*.ts", "src/**/*.vue"]
}
```

运行时必须允许外部 mapper 代码：

```bash
bunx --no-install tsrs --runExternalCode --noEmit -p tsconfig.json
bunx --no-install tsrs --runExternalCode --noEmit --fast -p tsconfig.json
```

`contentMappers` 属于 tsconfig 顶层配置；Vue 的 `target`、`plugins` 等选项放在 mapper 的 `options` 中。这个版本的 mapper 不读取顶层 `vueCompilerOptions`。**v4 已移除 `strictTemplates`**：模板检查跟随脚本语言的 TypeScript 检查设置，本例使用 `compilerOptions.strict: true`。从旧版 `vue-tsc` 迁移时不要直接复制该选项。`--fast` 是命令行开关，不能放进 `compilerOptions`。

mapper 把 `.vue` 转成类型检查用的虚拟 TypeScript，再把诊断位置映射回原始 `.vue`。不需要声明把所有 `.vue` 当作宽泛 `DefineComponent` 的 shim，否则会掩盖组件类型问题；本例也不需要生成中间 `.ts` 文件或手工调用 mapper。

## 确认 Vue 文件确实被检查

`examples/type-errors/` 有三个故意写错的组件：

- `ScriptError.vue`：把 string 赋给 number，预期 TS2322。
- `TemplateError.vue`：模板访问不存在的属性，预期 TS2339。
- `PropsError.vue`：把 number 传给要求 string 的组件 prop，预期 TS2322。

它们不在应用的默认 `include` 中，不会影响正常开发或构建。可以直接查看诊断：

```bash
bun run typecheck:errors
```

这个命令**预期以非零状态退出**，并报告这三个 `.vue` 文件中的错误。自动验证使用：

```bash
bun run test
```

验证脚本分别运行 tsrs 普通模式、`--fast` 和官方 TypeScript 7.1，断言三个错误都被发现、诊断仍指向原始 `.vue`；预期错误全部检出时返回 0。

## 编辑器与版本说明

VS Code 推荐安装 Vue - Official（`Vue.volar`），本项目提供了扩展推荐和 tsrs 自带的 tsconfig JSON schema。命令行使用 tsrs，不代表编辑器的 Vue 语言服务也自动切换到了 tsrs；此示例重点验证 CLI 检查流程。

当前 mapper 是 alpha，TypeScript 是 7.1 beta。升级时建议一起核对 tsrs 对应的 TS 版本、mapper 的 peer dependency，并运行 `bun run test` 和 `bun run bench:quick` 验证诊断与大负载检查。

官方参考：[tsrs 用法](https://github.com/oxc-project/tsrs/blob/main/docs/USAGE.md)、[Vue mapper npm 页面](https://www.npmjs.com/package/@vue/content-mapper)。安装后的完整 mapper 文档位于 `node_modules/@vue/content-mapper/README.md`。
