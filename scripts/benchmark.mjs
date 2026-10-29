import assert from 'node:assert/strict'
import { spawnSync } from 'node:child_process'
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs'
import { availableParallelism, cpus, totalmem } from 'node:os'
import { relative, resolve } from 'node:path'
import { performance } from 'node:perf_hooks'
import { fileURLToPath } from 'node:url'
import { parseArgs } from 'node:util'
import { verifyCorpus } from './generate-benchmark.mjs'

const root = fileURLToPath(new URL('../', import.meta.url))
const { values } = parseArgs({
  options: {
    runs: { type: 'string', default: '3' },
    warmup: { type: 'string', default: '1' },
    only: { type: 'string' },
  },
})
const runs = Number(values.runs)
const warmup = Number(values.warmup)
assert.ok(Number.isInteger(runs) && runs > 0, '--runs must be a positive integer')
assert.ok(Number.isInteger(warmup) && warmup >= 0, '--warmup must be a nonnegative integer')

const compilers = [
  { id: 'tsrs', name: 'tsrs', bin: 'tsrs/bin/tsrs', options: [] },
  { id: 'fast', name: 'tsrs --fast', bin: 'tsrs/bin/tsrs', options: ['--fast'] },
  { id: 'tsc', name: 'TS 7.1 + Vue mapper', bin: 'typescript/bin/tsc', options: [] },
].filter(compiler => !values.only || compiler.id === values.only)
assert.ok(compilers.length, '--only must be tsrs, fast, or tsc')

const corpus = verifyCorpus()
const workers = Number(process.env.VUE_CONTENT_MAPPER_WORKERS ?? Math.min(4, availableParallelism()))
assert.ok(Number.isInteger(workers) && workers > 0, 'VUE_CONTENT_MAPPER_WORKERS must be a positive integer')
const directory = resolve(root, 'benchmark/results', new Date().toISOString().replaceAll(':', '-'))
mkdirSync(directory, { recursive: true })
const records = []
const samples = new Map(compilers.map(compiler => [compiler.id, []]))

function run(compiler, phase, round) {
  const bin = resolve(root, 'node_modules', compiler.bin)
  const args = [
    bin,
    '--runExternalCode',
    '--noEmit',
    '--pretty', 'false',
    '--extendedDiagnostics',
    '-p', 'tsconfig.benchmark.json',
    ...compiler.options,
  ]
  console.log(`开始 ${phase === 'warmup' ? '预热' : '计时'} ${round}: ${compiler.name}`)
  const start = performance.now()
  const result = spawnSync('node', args, {
    cwd: root,
    encoding: 'utf8',
    maxBuffer: 16 * 1024 * 1024,
    env: {
      ...process.env,
      TSRS_FAST: '0',
      VUE_CONTENT_MAPPER_WORKERS: String(workers),
    },
  })
  const elapsedMs = performance.now() - start
  const log = resolve(directory, `${compiler.id}-${phase}-${round}.log`)
  const output = `${result.stdout ?? ''}${result.stderr ?? ''}`
  writeFileSync(log, output)
  assert.ifError(result.error)
  assert.equal(result.signal, null, `${compiler.name} exited with a signal; see ${relative(root, log)}`)
  assert.equal(result.status, 0, `${compiler.name} failed; see ${relative(root, log)}\n${output.slice(-8000)}`)
  records.push({ compiler: compiler.id, phase, round, elapsedMs, log: relative(root, log) })
  if (phase === 'run') samples.get(compiler.id).push(elapsedMs)
  console.log(`完成 ${compiler.name}: ${(elapsedMs / 1000).toFixed(3)} s`)
}

console.log(`负载：${corpus.tsFiles} TS + ${corpus.vueFiles} Vue × ${corpus.linesPerFile} 行，共 ${corpus.totalLines.toLocaleString('en-US')} 行`)
console.log(`每项预热 ${warmup} 次，计时 ${runs} 次；mapper workers=${workers}；各项顺序执行`)
for (let round = 1; round <= warmup; round++) {
  for (const compiler of compilers) run(compiler, 'warmup', round)
}
for (let round = 1; round <= runs; round++) {
  const offset = (round - 1) % compilers.length
  const order = compilers.slice(offset).concat(compilers.slice(0, offset))
  for (const compiler of order) run(compiler, 'run', round)
}

function median(values) {
  const sorted = [...values].sort((left, right) => left - right)
  const middle = Math.floor(sorted.length / 2)
  return sorted.length % 2 ? sorted[middle] : (sorted[middle - 1] + sorted[middle]) / 2
}

const results = compilers.map(compiler => {
  const elapsedMs = samples.get(compiler.id)
  return {
    compiler: compiler.id,
    name: compiler.name,
    medianMs: median(elapsedMs),
    minMs: Math.min(...elapsedMs),
    maxMs: Math.max(...elapsedMs),
    samplesMs: elapsedMs,
  }
})
const packageVersion = name => JSON.parse(readFileSync(resolve(root, 'node_modules', name, 'package.json'), 'utf8')).version
const report = {
  schemaVersion: 1,
  createdAt: new Date().toISOString(),
  corpus,
  runs,
  warmup,
  mapperWorkers: workers,
  measurement: 'Fresh compiler process wall time, including content mapper and worker startup; filesystem caches are not cleared. Warmups are excluded.',
  configuration: { project: 'tsconfig.benchmark.json', strict: true, skipLibCheck: true, incremental: false, noEmit: true },
  environment: {
    platform: process.platform,
    arch: process.arch,
    cpu: cpus()[0]?.model,
    availableParallelism: availableParallelism(),
    totalMemoryBytes: totalmem(),
    node: spawnSync('node', ['--version'], { encoding: 'utf8' }).stdout.trim(),
    bun: process.versions.bun,
  },
  versions: { tsrs: packageVersion('tsrs'), typescript: packageVersion('typescript'), mapper: packageVersion('@vue/content-mapper'), vue: packageVersion('vue') },
  results,
  records,
}
writeFileSync(resolve(directory, 'summary.json'), JSON.stringify(report, null, 2) + '\n')
writeFileSync(resolve(root, 'benchmark/results/latest.json'), JSON.stringify(report, null, 2) + '\n')
console.table(results.map(result => ({
  '检查器': result.name,
  '中位数(s)': (result.medianMs / 1000).toFixed(3),
  '最短(s)': (result.minMs / 1000).toFixed(3),
  '最长(s)': (result.maxMs / 1000).toFixed(3),
  '各轮(s)': result.samplesMs.map(value => (value / 1000).toFixed(3)).join(', '),
})))
console.log('计时包含编译器和 mapper 启动；未清除操作系统文件缓存。')
console.log(`结果：${relative(root, directory)}/summary.json`)
console.log('最近结果：benchmark/results/latest.json')
