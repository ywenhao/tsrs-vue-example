import assert from 'node:assert/strict'
import { createHash } from 'node:crypto'
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs'
import { dirname, relative, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { verifyCorpus } from './generate-benchmark.mjs'

export const projectRoot = fileURLToPath(new URL('../', import.meta.url))
export const scenarios = [
  { id: 'small-balanced', name: '100 TS + 100 Vue', ts: 100, vue: 100 },
  { id: 'ts-heavy', name: '600 TS + 200 Vue', ts: 600, vue: 200 },
  { id: 'vue-heavy', name: '200 TS + 600 Vue', ts: 200, vue: 600 },
  { id: 'large-balanced', name: '600 TS + 600 Vue', ts: 600, vue: 600 },
]
export const compilers = [
  { id: 'vue-tsc', name: 'vue-tsc + TS 6', bin: 'benchmark/toolchains/vue-tsc/node_modules/vue-tsc/bin/vue-tsc.js', external: false, options: [], color: '#94a3b8' },
  { id: 'tsc', name: 'TS 7.1 + Vue mapper', bin: 'node_modules/typescript/bin/tsc', external: true, options: [], color: '#60a5fa' },
  { id: 'tsrs', name: 'tsrs + Vue mapper', bin: 'node_modules/tsrs/bin/tsrs', external: true, options: [], color: '#fdba74' },
  { id: 'fast', name: 'tsrs --fast + mapper', bin: 'node_modules/tsrs/bin/tsrs', external: true, options: ['--fast'], color: '#f97316' },
]

const number = index => String(index).padStart(4, '0')
const slash = path => path.replaceAll('\\', '/')
const version = name => JSON.parse(readFileSync(resolve(projectRoot, name, 'package.json'), 'utf8')).version

export function toolchainVersions() {
  return {
    tsrs: version('node_modules/tsrs'),
    typescript: version('node_modules/typescript'),
    mapper: version('node_modules/@vue/content-mapper'),
    vue: version('node_modules/vue'),
    vueTsc: version('benchmark/toolchains/vue-tsc/node_modules/vue-tsc'),
    typescript6: version('benchmark/toolchains/vue-tsc/node_modules/typescript'),
  }
}

export function prepareSuite(selectedIds) {
  const corpus = verifyCorpus()
  const chosen = scenarios.filter(scenario => !selectedIds || selectedIds.includes(scenario.id))
  assert.ok(chosen.length, 'No matching scenarios')
  if (selectedIds) assert.equal(chosen.length, selectedIds.length, 'Unknown or duplicate scenario')
  const rootConfig = JSON.parse(readFileSync(resolve(projectRoot, 'tsconfig.json'), 'utf8'))
  const compilerOptions = { ...rootConfig.compilerOptions, incremental: false }
  const directory = resolve(projectRoot, 'benchmark/configs')
  mkdirSync(directory, { recursive: true })

  function writeConfig(id, files, legacy) {
    const name = `${id}-${legacy ? 'ts6' : 'mapper'}.json`
    const config = {
      compilerOptions,
      files: files.map(file => slash(relative(directory, file))),
      include: [],
      ...(legacy ? { vueCompilerOptions: { strictTemplates: true } } : { contentMappers: rootConfig.contentMappers }),
    }
    const path = resolve(directory, name)
    writeFileSync(path, JSON.stringify(config, null, 2) + '\n')
    return slash(relative(projectRoot, path))
  }

  const profiles = chosen.map(scenario => {
    const files = [
      ...Array.from({ length: scenario.ts }, (_, index) => resolve(projectRoot, `benchmark/generated/models/entity-${number(index)}.ts`)),
      ...Array.from({ length: scenario.vue }, (_, index) => resolve(projectRoot, `benchmark/generated/components/Component${number(index)}.vue`)),
    ]
    const selected = new Set(files)
    const hash = createHash('sha256')
    for (const file of files) {
      const content = readFileSync(file, 'utf8')
      assert.equal(content.split('\n').length - 1, 500, file)
      hash.update(slash(relative(projectRoot, file)) + '\0' + content)
      for (const match of content.matchAll(/^import[^\n]*from ['"]([^'"]+)['"]/gm)) {
        if (!match[1].startsWith('.')) continue
        const target = resolve(dirname(file), match[1] + (match[1].endsWith('.vue') ? '' : '.ts'))
        assert.ok(selected.has(target), `${scenario.id} imports source outside its selected files: ${target}`)
      }
    }
    return {
      ...scenario,
      linesPerFile: 500,
      totalLines: (scenario.ts + scenario.vue) * 500,
      sourceSha256: hash.digest('hex'),
      configs: { legacy: writeConfig(scenario.id, files, true), mapper: writeConfig(scenario.id, files, false) },
    }
  })
  const errors = ['ScriptError.vue', 'TemplateError.vue', 'PropsError.vue'].map(name => resolve(projectRoot, 'examples/type-errors', name))
  const preflight = { legacy: writeConfig('preflight', errors, true), mapper: writeConfig('preflight', errors, false) }
  return { corpus, compilerOptions, profiles, preflight }
}
