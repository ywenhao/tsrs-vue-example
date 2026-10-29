import assert from 'node:assert/strict'
import { spawnSync } from 'node:child_process'
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs'
import { availableParallelism, cpus, release, totalmem } from 'node:os'
import { relative, resolve } from 'node:path'
import { parseArgs } from 'node:util'
import { compilers, prepareSuite, projectRoot, toolchainVersions } from './benchmark-suite-config.mjs'

const { values } = parseArgs({ options: {
  runs: { type: 'string', default: '3' },
  warmup: { type: 'string', default: '1' },
  scenarios: { type: 'string' },
  resume: { type: 'string' },
  'no-render': { type: 'boolean', default: false },
} })
assert.equal(process.platform, 'linux', 'Memory sampling requires Linux or WSL')
const runs = Number(values.runs)
const warmup = Number(values.warmup)
assert.ok(Number.isInteger(runs) && runs > 0, '--runs must be positive')
assert.ok(Number.isInteger(warmup) && warmup >= 0, '--warmup must be nonnegative')
const selectedIds = values.scenarios?.split(',')
const suite = prepareSuite(selectedIds)
const versions = toolchainVersions()
assert.equal(versions.typescript6, '6.0.3')
const workers = Number(process.env.VUE_CONTENT_MAPPER_WORKERS ?? Math.min(4, availableParallelism()))
assert.ok(Number.isInteger(workers) && workers > 0)
const environment = { ...process.env, NODE_OPTIONS: '--max-old-space-size=8192', TSRS_FAST: '0', VUE_CONTENT_MAPPER_WORKERS: String(workers) }
const output = values.resume
  ? resolve(projectRoot, values.resume)
  : resolve(projectRoot, 'benchmark/reports', new Date().toISOString().replaceAll(':', '-'))
mkdirSync(output, { recursive: true })
const checkpoint = resolve(output, 'results.json')
let report = {
  schemaVersion: 2,
  createdAt: new Date().toISOString(),
  status: 'running',
  runs,
  warmup,
  mapperWorkers: workers,
  versions,
  scenarios: suite.profiles,
  compilers: compilers.map(({ id, name, color }) => ({ id, name, color })),
  compilerOptions: suite.compilerOptions,
  methodology: {
    timing: 'Fresh compiler process wall time, including compiler, Vue transforms and mapper startup; warmups excluded; filesystem caches not cleared.',
    memory: 'Peak simultaneously sampled compiler-process-tree RSS, including mapper/API child processes; sum may count shared pages more than once; monitoring/coordinator excluded.',
    memoryAggregation: 'Median of per-run sampled peaks; min/max and all raw peaks are retained.',
    sampleIntervalMs: 25,
    nodeHeapLimitMiB: 8192,
    sourceValidation: 'Exact 500 physical lines per source file; every relative project import stays inside the selected scenario.',
    scheduling: 'One compiler at a time; compiler order rotates each measured round.',
  },
  environment: {
    platform: process.platform, arch: process.arch, release: release(), cpu: cpus()[0]?.model,
    availableParallelism: availableParallelism(), totalMemoryBytes: totalmem(),
    node: spawnSync('node', ['--version'], { encoding: 'utf8' }).stdout.trim(), bun: process.versions.bun,
    python: spawnSync('python3', ['--version'], { encoding: 'utf8' }).stdout.trim(),
  },
  preflight: [],
  records: [],
}
if (values.resume) {
  const previous = JSON.parse(readFileSync(checkpoint, 'utf8'))
  assert.equal(previous.runs, runs, 'Resume must use the same --runs')
  assert.equal(previous.warmup, warmup, 'Resume must use the same --warmup')
  assert.deepEqual(previous.versions, versions, 'Toolchain versions changed')
  assert.deepEqual(previous.scenarios.map(x => [x.id, x.sourceSha256]), suite.profiles.map(x => [x.id, x.sourceSha256]), 'Scenario sources changed')
  assert.equal(previous.mapperWorkers, workers, 'Worker count changed')
  report = { ...previous, status: 'running' }
}
function save() {
  writeFileSync(checkpoint, JSON.stringify(report, null, 2) + '\n')
}
function args(compiler, config, diagnostics = true) {
  return [
    resolve(projectRoot, compiler.bin),
    ...(compiler.external ? ['--runExternalCode'] : []),
    '--noEmit', '--pretty', 'false',
    ...(diagnostics ? ['--extendedDiagnostics'] : []),
    '-p', config,
    ...compiler.options,
  ]
}

save()
console.log(`报告目录：${relative(projectRoot, output)}`)
for (const compiler of compilers) {
  if (report.preflight.some(item => item.compiler === compiler.id && item.passed)) continue
  const config = compiler.external ? suite.preflight.mapper : suite.preflight.legacy
  const result = spawnSync('node', args(compiler, config, false), { cwd: projectRoot, env: environment, encoding: 'utf8', maxBuffer: 4 * 1024 * 1024 })
  assert.ifError(result.error)
  const text = `${result.stdout ?? ''}${result.stderr ?? ''}`
  writeFileSync(resolve(output, `${compiler.id}-preflight.log`), text)
  assert.notEqual(result.status, 0, `${compiler.name} missed the intentional errors`)
  for (const [file, code] of [['ScriptError', 2322], ['TemplateError', 2339], ['PropsError', 2322]]) {
    assert.match(text, new RegExp(`${file}\\.vue\\(\\d+,\\d+\\): error TS${code}\\b`), text)
  }
  assert.equal((text.match(/error TS\d+/g) ?? []).length, 3, text)
  report.preflight.push({ compiler: compiler.id, passed: true, expectedDiagnostics: 3 })
  save()
  console.log(`预检通过：${compiler.name} 检出全部 3 个预期错误`)
}

function run(scenario, compiler, phase, round) {
  const key = `${scenario.id}/${compiler.id}/${phase}/${round}`
  if (report.records.some(item => item.key === key && item.exitCode === 0 && !item.timedOut)) return
  const name = `${scenario.id}-${compiler.id}-${phase}-${round}`
  const logPath = resolve(output, `${name}.log`)
  const metricsPath = resolve(output, `${name}.json`)
  const config = compiler.external ? scenario.configs.mapper : scenario.configs.legacy
  console.log(`开始 ${scenario.name} | ${compiler.name} | ${phase} ${round}`)
  const measured = spawnSync('python3', [
    resolve(projectRoot, 'scripts/measure-process.py'),
    '--output', metricsPath, '--log', logPath, '--cwd', projectRoot,
    '--interval-ms', '25', '--', 'node', ...args(compiler, config),
  ], { cwd: projectRoot, env: environment, encoding: 'utf8', maxBuffer: 1024 * 1024 })
  assert.ifError(measured.error)
  assert.equal(measured.status, 0, `${measured.stdout ?? ''}${measured.stderr ?? ''}`)
  const metrics = JSON.parse(readFileSync(metricsPath, 'utf8'))
  const text = readFileSync(logPath, 'utf8')
  const seconds = label => {
    const match = text.match(new RegExp(`^${label}:\\s+([\\d.]+)s`, 'm'))
    return match ? Number(match[1]) * 1000 : null
  }
  const record = {
    key, scenario: scenario.id, compiler: compiler.id, phase, round, ...metrics,
    checkMs: seconds('Check time'), mapperWaitMs: seconds('Content mapper request wait time'),
    log: relative(output, logPath), metrics: relative(output, metricsPath),
  }
  report.records = report.records.filter(item => item.key !== key).concat(record)
  save()
  assert.equal(metrics.exitCode, 0, `${compiler.name} failed: ${text.slice(-6000)}`)
  assert.equal(metrics.timedOut, false, 'Compiler timed out')
  assert.ok(metrics.peakRssBytes > 0 && metrics.samples > 0)
  console.log(`完成 ${(metrics.wallMs / 1000).toFixed(3)} s | 峰值进程树 RSS ${(metrics.peakRssBytes / 1024 / 1024).toFixed(1)} MiB | 最多 ${metrics.maxProcesses} 个进程`)
}

for (const scenario of suite.profiles) {
  for (let round = 1; round <= warmup; round++) {
    for (const compiler of compilers) run(scenario, compiler, 'warmup', round)
  }
  for (let round = 1; round <= runs; round++) {
    const offset = (round - 1) % compilers.length
    for (const compiler of compilers.slice(offset).concat(compilers.slice(0, offset))) run(scenario, compiler, 'run', round)
  }
}
report.status = 'complete'
report.completedAt = new Date().toISOString()
save()
const pointer = resolve(projectRoot, 'benchmark/reports/latest-run.json')
writeFileSync(pointer, JSON.stringify({ directory: relative(projectRoot, output), results: relative(projectRoot, checkpoint) }, null, 2) + '\n')
console.log(`所有场景完成：${relative(projectRoot, checkpoint)}`)
if (!values['no-render']) {
  const render = spawnSync('uv', ['run', '--no-build', '--python', '3.14', '--script', 'scripts/render-benchmark-report.py', checkpoint], { cwd: projectRoot, stdio: 'inherit' })
  assert.equal(render.status, 0, 'Rendering failed; raw results are preserved and can be rendered again')
}
