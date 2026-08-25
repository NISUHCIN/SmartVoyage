<script setup>
defineProps({
  loading: Boolean,
  error: String,
  reply: String,
  title: { type: String, default: '查询结果' }
})
</script>

<template>
  <section class="panel result-panel">
    <header class="panel-header">
      <h2>{{ title }}</h2>
      <span v-if="loading" class="status-badge loading">处理中</span>
      <span v-else-if="reply" class="status-badge ok">完成</span>
      <span v-else class="status-badge idle">待查询</span>
    </header>
    <div v-if="loading" class="result-body">
      <span class="spinner"></span>
    </div>
    <p v-else-if="error" class="error-text">{{ error }}</p>
    <pre v-else-if="reply" class="result-text">{{ reply }}</pre>
    <p v-else class="empty-text">提交查询后，结果会显示在这里。</p>
  </section>
</template>
