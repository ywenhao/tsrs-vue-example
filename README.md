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
