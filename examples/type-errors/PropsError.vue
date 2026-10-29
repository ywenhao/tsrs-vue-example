<script setup lang="ts">
import { ref } from 'vue'
import CounterCard from '../../src/components/CounterCard.vue'

const count = ref(0)
</script>

<template>
  <!-- 故意写错：title 要求 string，这里传入 number。 -->
  <CounterCard v-model="count" :title="123" />
</template>
