<script setup>
import { computed, ref } from 'vue'
import CitySelect from '../components/CitySelect.vue'
import QueryResult from '../components/QueryResult.vue'
import { queryTicket, queryTicketOrder } from '../api'
import Icon from '../components/Icon.vue'

const mode = ref('train')
const fromCity = ref('')
const toCity = ref('')
const city = ref('')
const keyword = ref('')
const date = ref('')
const loading = ref(false)
const reply = ref('')
const error = ref('')

const modes = [
  { key: 'train', label: '火车/高铁' }
]

const modeLabel = computed(() => modes.find((m) => m.key === mode.value)?.label || '')

function validate() {
  if (mode.value === 'concert') {
    return city.value ? '' : '请选择演出城市'
  }
  if (!fromCity.value || !toCity.value) return '请选择出发和到达城市'
  return ''
}

function buildMessage(book = false) {
  const day = date.value || '今天'
  if (mode.value === 'concert') {
    const subject = keyword.value ? ` ${keyword.value}` : ''
    return book
      ? `帮我订${city.value}${day}${subject}的演出门票`
      : `查询${city.value}${day}${subject}的演出门票`
  }
  const type = mode.value === 'train' ? '火车票' : '机票'
  return book
    ? `帮我订${day}从${fromCity.value}到${toCity.value}的${type}`
    : `查询${day}从${fromCity.value}到${toCity.value}的${type}`
}

async function run(book) {
  const invalid = validate()
  if (invalid) {
    error.value = invalid
    return
  }
  error.value = ''
  loading.value = true
  reply.value = ''
  try {
    const data = book
      ? await queryTicketOrder(buildMessage(true))
      : await queryTicket(buildMessage(false))
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
      <h1>票务</h1>
      <p class="muted">查询或预订火车、飞机与演出票</p>
    </header>
    <section class="panel">
      <div class="segmented">
        <button v-for="m in modes" :key="m.key" :class="{ active: mode === m.key }" @click="mode = m.key">
          {{ m.label }}
        </button>
      </div>
      <div class="form-grid ticket-grid">
        <template v-if="mode === 'concert'">
          <CitySelect v-model="city" />
          <label class="field-label">日期<input v-model="date" type="date" class="text-input" /></label>
          <label class="field-label">关键词<input v-model="keyword" class="text-input" placeholder="歌手或演出名称" /></label>
        </template>
        <template v-else>
          <CitySelect v-model="fromCity" />
          <CitySelect v-model="toCity" />
          <label class="field-label">日期<input v-model="date" type="date" class="text-input" /></label>
        </template>
        <div class="button-row">
          <button class="primary-button" :disabled="loading" @click="run(false)"><Icon name="search" :size="18" /> 查询</button>
          <button class="secondary-button" :disabled="loading" @click="run(true)"><Icon name="bag" :size="18" /> 订票</button>
        </div>
      </div>
    </section>
    <QueryResult :loading="loading" :error="error" :reply="reply" :title="modeLabel + '结果'" />
  </div>
</template>

<style scoped>
.ticket-grid {
  margin-top: 14px;
}
.button-row {
  display: flex;
  gap: 8px;
}
</style>
