import assert from 'node:assert/strict'
import { spawnSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'

const root = fileURLToPath(new URL('../', import.meta.url))
const compilers = [
  { name: 'tsrs', bin: 'tsrs/bin/tsrs', options: [] },
  { name: 'tsrs --fast', bin: 'tsrs/bin/tsrs', options: ['--fast'] },
  { name: 'TypeScript 7.1', bin: 'typescript/bin/tsc', options: [] },
]
const expectedErrors = [
  { file: 'ScriptError.vue', code: 2322 },
  { file: 'TemplateError.vue', code: 2339 },
  { file: 'PropsError.vue', code: 2322 },
]

for (const compiler of compilers) {
  const bin = fileURLToPath(new URL(`../node_modules/${compiler.bin}`, import.meta.url))
  const result = spawnSync('node', [
    bin,
    '--runExternalCode',
    '--noEmit',
    '--pretty', 'false',
    '-p', 'tsconfig.errors.json',
    ...compiler.options,
  ], {
    cwd: root,
    encoding: 'utf8',
    timeout: 60_000,
  })

  assert.ifError(result.error)
  assert.equal(result.signal, null, `${compiler.name} exited with a signal`)
  assert.notEqual(result.status, 0, `${compiler.name} missed the intentional errors`)
  const output = `${result.stdout}\n${result.stderr}`

  for (const { file, code } of expectedErrors) {
    const pattern = new RegExp(`${file.replaceAll('.', '\\.')}\\(\\d+,\\d+\\): error TS${code}\\b`)
    assert.match(output, pattern, `${compiler.name} did not map TS${code} to ${file}:\n${output}`)
  }
  assert.equal((output.match(/error TS\d+/g) ?? []).length, expectedErrors.length, output)
  console.log(`✓ ${compiler.name}: detected all 3 intentional errors at their original .vue locations`)
}
