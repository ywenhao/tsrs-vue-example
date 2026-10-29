<script setup lang="ts">
import { computed, ref } from 'vue'
import CounterCard from './components/CounterCard.vue'
import { formatCount } from './lib/counter'

const count = ref(0)
const lastChange = ref<number | null>(null)
const message = computed(() => lastChange.value === null
  ? '点击按钮，子组件会通过 change 事件把数值传给父组件。'
  : `父组件收到 change(${formatCount(lastChange.value)})。`)

function handleChange(value: number): void {
  lastChange.value = value
}

function reset(): void {
  count.value = 0
  lastChange.value = null
}
</script>

<template>
  <main>
    <header>
      <span class="eyebrow">VUE SINGLE-FILE COMPONENTS</span>
      <h1>tsrs + Vue mapper</h1>
      <p>一个包含类型化 props、v-model 和事件的 Vue 示例。</p>
    </header>

    <CounterCard
      v-model="count"
      title="类型安全的计数器"
      :step="2"
      @change="handleChange"
    />

    <section class="status" aria-live="polite">
      <p>{{ message }}</p>
      <button class="text-button" type="button" @click="reset">重置</button>
    </section>

    <footer>
      <p>普通检查 <code>bun run typecheck</code></p>
      <p>快速检查 <code>bun run typecheck:fast</code></p>
      <p>对比耗时 <code>bun run bench</code></p>
      <p>验证错误检测 <code>bun run test</code></p>
    </footer>
  </main>
</template>
