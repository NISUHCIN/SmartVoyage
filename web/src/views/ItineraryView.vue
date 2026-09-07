<script setup>
import { computed, ref } from 'vue'
import CitySelect from '../components/CitySelect.vue'
import Icon from '../components/Icon.vue'
import {
  queryItinerary,
  searchHotels,
  searchTrains,
  searchWeatherStructured,
} from '../api'

function nextDay() {
  const day = new Date(Date.now() + 86400000)
  const pad = (n) => String(n).padStart(2, '0')
  return `${day.getFullYear()}-${pad(day.getMonth() + 1)}-${pad(day.getDate())}`
}

const fromCity = ref('上海')
const city = ref('杭州')
const startDate = ref(nextDay())
const days = ref(2)
const budget = ref(2000)
const preference = ref('轻装快玩，高铁当天往返附近景点')
const loading = ref(false)
const error = ref('')
const reply = ref('')
const daysRows = ref([])
const weatherRows = ref([])
const trainRows = ref([])
const hotelRows = ref([])
const sourceSummary = ref([])

const budgetTotal = computed(() => Number(budget.value || 0) * Number(days.value || 1))

function fmtTime(value) {
  return value ? String(value).slice(0, 16) : '--'
}

function money(value) {
  const num = Number(value)
  return Number.isFinite(num) ? `¥${num.toFixed(num % 1 === 0 ? 0 : 2)}` : '--'
}

async function query() {
  error.value = ''
  reply.value = ''
  daysRows.value = []
  weatherRows.value = []
  trainRows.value = []
  hotelRows.value = []
  sourceSummary.value = []
  if (!fromCity.value || !city.value || fromCity.value === city.value) {
    error.value = '请选择不同的出发城市和目的地'
    return
  }
  if (!startDate.value) {
    error.value = '请选择出发日期'
    return
  }
  loading.value = true
  const preferenceText = preference.value ? `，偏好${preference.value}` : ''
  const budgetText = budget.value ? `，整段预算约${budget.value}元` : ''
  const itineraryMessage =
    `从${fromCity.value}到${city.value}，${startDate.value}出发，规划${days.value}天行程${preferenceText}${budgetText}`

  const tasks = {
    itinerary: queryItinerary(itineraryMessage),
    weather: searchWeatherStructured({
      city: city.value,
      date: startDate.value,
      days: Number(days.value),
    }),
    trains: searchTrains({
      departure_city: fromCity.value,
      arrival_city: city.value,
      travel_date: startDate.value,
      seat_type: '二等座',
    }),
    hotels: searchHotels({
      city: city.value,
      check_in: startDate.value,
      nights: Number(days.value),
      adults: 2,
    }),
  }
  try {
    const entries = Object.entries(tasks).map(([key, promise]) => ({
      key,
      promise: promise.then((data) => ({ key, data })),
    }))
    const settled = await Promise.allSettled(entries.map((entry) => entry.promise))
    for (const [index, item] of settled.entries()) {
      const key = entries[index].key
      if (item.status === 'rejected') {
        sourceSummary.value.push({ key, source: '不可用', degraded: true })
        continue
      }
      const settledKey = key
      const data = item.value.data
      if (settledKey === 'itinerary') {
        reply.value = data.reply || ''
        daysRows.value = (data.data && data.data.days) || []
        if (daysRows.value.length && data.data) {
          sourceSummary.value.push({ key: '行程 Agent', source: 'A2A 编排', degraded: false })
        }
      } else if (settledKey === 'weather') {
        weatherRows.value = (data.rows || []).slice(0, 7)
        sourceSummary.value.push({
          key: '天气',
          source: data.source || '实时天气',
          degraded: Boolean(data.degraded),
        })
      } else if (settledKey === 'trains') {
        trainRows.value = (data.rows || []).slice(0, 4)
        sourceSummary.value.push({
          key: '班次',
          source: data.source || '真实余票',
          degraded: Boolean(data.degraded),
        })
      } else if (settledKey === 'hotels') {
        hotelRows.value = (data.rows || []).slice(0, 4)
        sourceSummary.value.push({
          key: '酒店',
          source: data.source || '酒店数据',
          degraded: Boolean(data.degraded),
        })
      }
    }
    if (!daysRows.value.length && reply.value) {
      error.value = ''
    }
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
      <div>
        <h1>行程规划</h1>
        <p class="muted">真实天气 + 真实班次 + 真实酒店 + 预算，生成结构化多日时间线</p>
      </div>
      <div v-if="sourceSummary.length" class="status-chips source-chips">
        <span
          v-for="(src, i) in sourceSummary"
          :key="i"
          class="chip"
          :class="{ degraded: src.degraded }"
        >
          <Icon name="wifi" :size="14" />
          {{ src.key }}：{{ src.source }}{{ src.degraded ? '（降级）' : '' }}
        </span>
      </div>
    </header>

    <section class="panel">
      <div class="form-grid itinerary-grid">
        <CitySelect v-model="fromCity" />
        <CitySelect v-model="city" />
        <label class="field-label">出发日期<input v-model="startDate" type="date" class="text-input" /></label>
        <label class="field-label">天数
          <select v-model.number="days" class="select-input">
            <option v-for="n in 7" :key="n" :value="n">{{ n }} 天</option>
          </select>
        </label>
        <label class="field-label">预算（元）<input v-model.number="budget" type="number" min="100" class="text-input" /></label>
        <label class="field-label">偏好<input v-model="preference" class="text-input" placeholder="如：亲子、美食、轻松" /></label>
        <button class="primary-button" :disabled="loading" @click="query">
          <Icon name="route" :size="18" /> {{ loading ? '规划中...' : '生成实时行程' }}
        </button>
      </div>
    </section>

    <div v-if="error" class="banner error-banner"><Icon name="alert" :size="16" /> {{ error }}</div>
    <div v-if="loading" class="panel itinerary-loading">
      <span class="spinner"></span>
      <p>正在并行调用天气 / 车次 / 酒店 / 行程 Agent...</p>
    </div>

    <template v-if="!loading && (daysRows.length || reply)">
      <section v-if="daysRows.length" class="section">
        <header class="section-head">
          <h2>结构化时间线</h2>
          <span class="status-badge ok">{{ fromCity }} → {{ city }}</span>
        </header>
        <div class="timeline">
          <article v-for="day in daysRows" :key="day.day || day.date" class="day-card panel">
            <div class="day-rail">
              <span class="day-badge">Day {{ day.day || 1 }}</span>
              <span class="day-date">{{ day.date }}</span>
            </div>
            <div class="day-body">
              <div v-if="day.weather" class="day-block weather-block">
                <span class="block-label"><Icon name="weather" :size="15" /> 天气</span>
                <p>{{ day.weather }}</p>
              </div>
              <div v-if="day.transport" class="day-block">
                <span class="block-label"><Icon name="ticket" :size="15" /> 交通</span>
                <p>{{ day.transport }}</p>
              </div>
              <div v-if="day.hotel" class="day-block">
                <span class="block-label"><Icon name="bed" :size="15" /> 住宿</span>
                <p>{{ day.hotel }}</p>
              </div>
              <div v-if="day.attractions && day.attractions.length" class="day-block">
                <span class="block-label"><Icon name="pin" :size="15" /> 行程</span>
                <p v-for="(spot, si) in day.attractions" :key="si" class="spot-line">· {{ spot }}</p>
              </div>
            </div>
          </article>
        </div>
      </section>

      <section class="section">
        <header class="section-head">
          <h2>实时数据支撑</h2>
          <span class="status-badge ok">{{ budget ? `预算 ${budget}元/人 · 总计约 ${budgetTotal}元` : '' }}</span>
        </header>
        <div class="live-grid">
          <section v-if="weatherRows.length" class="live-panel panel">
            <h3>天气</h3>
            <div class="weather-strip">
              <article v-for="row in weatherRows" :key="row.fx_date" class="weather-day">
                <strong>{{ String(row.fx_date).slice(5) }}</strong>
                <span>{{ row.text_day || row.textDay }}</span>
                <b>{{ row.temp_min || row.tempMin }}° / {{ row.temp_max || row.tempMax }}°</b>
              </article>
            </div>
          </section>
          <section v-if="trainRows.length" class="live-panel panel">
            <h3>真实班次</h3>
            <div class="mini-table">
              <div v-for="row in trainRows" :key="row._booking_key || row.train_number" class="mini-row">
                <strong>{{ row.train_number }}</strong>
                <span>{{ row.departure_city }} {{ fmtTime(row.departure_time) }} → {{ row.arrival_city }} {{ fmtTime(row.arrival_time) }}</span>
                <span>{{ row.seat_type }} · {{ money(row.price) }} · {{ row.remaining_seats ?? row.remaining_text }}</span>
              </div>
            </div>
          </section>
          <section v-if="hotelRows.length" class="live-panel panel">
            <h3>酒店</h3>
            <div class="mini-list">
              <div v-for="row in hotelRows" :key="row._booking_key || row.hotel_name" class="hotel-mini">
                <strong>{{ row.hotel_name }}</strong>
                <span>{{ row.room_type || '最低价房型待查' }} · {{ money(row.price) }}/晚</span>
              </div>
            </div>
          </section>
        </div>
      </section>

      <section v-if="reply" class="panel text-panel">
        <header class="panel-header">
          <h2>Agent 完整规划说明</h2>
          <span class="status-badge ok">LLM 编排</span>
        </header>
        <pre class="result-text">{{ reply }}</pre>
      </section>
    </template>
  </div>
</template>

<style scoped>
.itinerary-grid {
  align-items: end;
}
.source-chips .chip.degraded {
  color: var(--accent);
  border-color: #fde68a;
}
.itinerary-loading {
  min-height: 180px;
  display: grid;
  place-items: center;
  align-content: center;
  gap: 12px;
  color: var(--muted);
}
.section {
  gap: 14px;
}
.section-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}
.section-head h2 {
  margin: 0;
  font-size: 17px;
}
.timeline {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.day-card {
  display: grid;
  grid-template-columns: 90px 1fr;
  gap: 14px;
}
.day-rail {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 6px;
  border-right: 1px solid var(--line);
  padding-right: 14px;
}
.day-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: var(--primary);
  color: #fff;
  font-size: 12px;
  font-weight: 700;
  border-radius: 999px;
  padding: 4px 10px;
}
.day-date {
  color: var(--muted);
  font-size: 13px;
}
.day-body {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
  gap: 12px;
}
.day-block {
  background: #f7f9fa;
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 10px 12px;
}
.block-label {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: var(--primary);
  font-size: 12px;
  font-weight: 700;
  margin-bottom: 4px;
}
.day-block p {
  margin: 0;
  color: var(--muted);
  font-size: 13px;
  line-height: 1.7;
  white-space: pre-wrap;
}
.spot-line {
  padding-left: 10px;
}
.live-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: 12px;
}
.live-panel h3 {
  margin: 0 0 10px;
  font-size: 14px;
}
.weather-strip {
  display: flex;
  gap: 6px;
  overflow-x: auto;
}
.weather-day {
  flex: 0 0 84px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 8px 4px;
  font-size: 12px;
}
.weather-day span {
  color: var(--muted);
}
.mini-row,
.hotel-mini {
  display: flex;
  flex-direction: column;
  gap: 3px;
  border-bottom: 1px solid var(--line);
  padding: 8px 0;
  font-size: 12px;
}
.mini-row:last-child,
.hotel-mini:last-child {
  border-bottom: 0;
}
.mini-row span,
.hotel-mini span {
  color: var(--muted);
}
.text-panel {
  display: flex;
  flex-direction: column;
}
@media (max-width: 640px) {
  .day-card {
    grid-template-columns: 1fr;
  }
  .day-rail {
    flex-direction: row;
    border-right: 0;
    border-bottom: 1px solid var(--line);
    padding: 0 0 8px;
  }
}
</style>
