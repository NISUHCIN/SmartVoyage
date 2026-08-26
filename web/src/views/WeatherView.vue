<script setup>
import { ref } from 'vue'
import CitySelect from '../components/CitySelect.vue'
import QueryResult from '../components/QueryResult.vue'
import { queryWeather } from '../api'
import Icon from '../components/Icon.vue'

const city = ref('')
const date = ref('')
const loading = ref(false)
const reply = ref('')
const rows = ref([])
const error = ref('')

async function query() {
  if (!city.value) {
    error.value = '请选择城市'
    return
  }
  error.value = ''
  loading.value = true
  reply.value = ''
  rows.value = []
  const message = date.value ? `${city.value} ${date.value} 天气` : `${city.value} 未来5天天气`
  try {
    const data = await queryWeather(message)
    reply.value = data.reply
    rows.value = data.data || []
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="view">
    <header class="view-header">
      <h1>天气查询</h1>
      <p class="muted">选择全国任意城市，查看实时或预报天气</p>
    </header>
    <section class="panel">
      <div class="form-grid">
        <CitySelect v-model="city" />
        <label class="field-label">日期<input v-model="date" type="date" class="text-input" /></label>
        <button class="primary-button" :disabled="loading" @click="query"><Icon name="search" :size="18" /> 查询</button>
      </div>
    </section>
    <QueryResult :loading="loading" :error="error" :reply="reply" :rows="rows" title="天气结果" />
  </div>
</template>
