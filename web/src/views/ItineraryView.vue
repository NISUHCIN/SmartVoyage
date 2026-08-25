<script setup>
import { ref } from 'vue'
import CitySelect from '../components/CitySelect.vue'
import QueryResult from '../components/QueryResult.vue'
import { queryItinerary } from '../api'
import Icon from '../components/Icon.vue'

const city = ref('')
const days = ref(3)
const preference = ref('')
const loading = ref(false)
const reply = ref('')
const error = ref('')

async function query() {
  if (!city.value) {
    error.value = '请选择城市'
    return
  }
  error.value = ''
  loading.value = true
  reply.value = ''
  const preferenceText = preference.value ? `，偏好${preference.value}` : ''
  const message = `规划${city.value}${days.value}天行程${preferenceText}`
  try {
    const data = await queryItinerary(message)
    reply.value = data.reply
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
      <h1>行程规划</h1>
      <p class="muted">生成多日旅行安排</p>
    </header>
    <section class="panel">
      <div class="form-grid">
        <CitySelect v-model="city" />
        <label class="field-label">天数<input v-model.number="days" type="number" min="1" max="15" class="text-input" /></label>
        <label class="field-label">偏好<input v-model="preference" class="text-input" placeholder="如：亲子、美食、自然风光" /></label>
        <button class="primary-button" :disabled="loading" @click="query"><Icon name="route" :size="18" /> 生成行程</button>
      </div>
    </section>
    <QueryResult :loading="loading" :error="error" :reply="reply" title="行程方案" />
  </div>
</template>
