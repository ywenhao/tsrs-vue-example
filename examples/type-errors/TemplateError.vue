<script setup lang="ts">
const user = { name: 'Ada' }
</script>

<template>
  <!-- 故意写错：模板访问不存在的属性。 -->
  <p>{{ user.notExists }}</p>
</template>
