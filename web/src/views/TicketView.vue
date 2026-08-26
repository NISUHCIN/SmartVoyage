<script setup>
import { ref } from 'vue'
import CitySelect from '../components/CitySelect.vue'
import QueryResult from '../components/QueryResult.vue'
import { queryTicket, queryTicketOrder } from '../api'
import Icon from '../components/Icon.vue'

const fromCity = ref('')
const toCity = ref('')
const date = ref('')
const loading = ref(false)
const reply = ref('')
const rows = ref([])
const error = ref('')

function validate() {
  if (!fromCity.value || !toCity.value) return '请选择出发和到达城市'
  return ''
}

function buildMessage(book = false) {
  const day = date.value || '今天'
  const type = '火车票'
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
  rows.value = []
  try {
    const data = book
      ? await queryTicketOrder(buildMessage(true))
      : await queryTicket(buildMessage(false))
    reply.value = data.reply
    rows.value = book ? [] : data.data || []
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
      <p class="muted">查询或预订火车/高铁票</p>
    </header>
    <section class="panel">
      <div class="form-grid ticket-grid">
        <CitySelect v-model="fromCity" />
        <CitySelect v-model="toCity" />
        <label class="field-label">日期<input v-model="date" type="date" class="text-input" /></label>
        <div class="button-row">
          <button class="primary-button" :disabled="loading" @click="run(false)"><Icon name="search" :size="18" /> 查询</button>
          <button class="secondary-button" :disabled="loading" @click="run(true)"><Icon name="bag" :size="18" /> 订票</button>
        </div>
      </div>
    </section>
    <QueryResult :loading="loading" :error="error" :reply="reply" :rows="rows" title="火车/高铁票结果" />
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
