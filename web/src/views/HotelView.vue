<script setup>
import { ref } from 'vue'
import CitySelect from '../components/CitySelect.vue'
import QueryResult from '../components/QueryResult.vue'
import { queryHotel } from '../api'
import Icon from '../components/Icon.vue'

const city = ref('')
const district = ref('')
const keyword = ref('')
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
  const districtText = district.value ? district.value : ''
  const keywordText = keyword.value ? `，${keyword.value}` : ''
  const message = `查询${city.value}${districtText}的酒店${keywordText}`
  try {
    const data = await queryHotel(message)
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
      <h1>酒店</h1>
      <p class="muted">按城市、区域与房型查找酒店</p>
    </header>
    <section class="panel">
      <div class="form-grid">
        <CitySelect v-model="city" />
        <label class="field-label">区域<input v-model="district" class="text-input" placeholder="如：天河区" /></label>
        <label class="field-label">偏好<input v-model="keyword" class="text-input" placeholder="如：大床房" /></label>
        <button class="primary-button" :disabled="loading" @click="query"><Icon name="search" :size="18" /> 查询</button>
      </div>
    </section>
    <QueryResult :loading="loading" :error="error" :reply="reply" :rows="rows" title="酒店结果" />
  </div>
</template>
