<script setup lang="ts">
import { computed } from 'vue'
import { formatCount } from '../lib/counter'

const { title, step = 1 } = defineProps<{
  title: string
  step?: number
}>()

const count = defineModel<number>({ required: true })
const emit = defineEmits<{
  change: [value: number]
}>()

const doubled = computed(() => count.value * 2)

function adjust(amount: number): void {
  count.value += amount
  emit('change', count.value)
}
</script>

<template>
  <section class="counter-card" aria-labelledby="counter-title">
    <h2 id="counter-title">{{ title }}</h2>
    <p class="counter-value" aria-live="polite">{{ formatCount(count) }}</p>
    <p class="muted">两倍值：{{ formatCount(doubled) }}</p>
    <div class="counter-actions">
      <button type="button" :aria-label="`减少 ${step}`" @click="adjust(-step)">− {{ step }}</button>
      <button type="button" :aria-label="`增加 ${step}`" @click="adjust(step)">+ {{ step }}</button>
    </div>
  </section>
</template>
