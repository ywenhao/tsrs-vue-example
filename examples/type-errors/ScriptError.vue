<script setup lang="ts">
// 故意写错：string 不能赋给 number。
const count: number = 'not-a-number'
</script>

<template>
  <p>{{ count }}</p>
</template>
