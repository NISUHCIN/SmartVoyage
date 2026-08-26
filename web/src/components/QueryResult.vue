<script setup>
import { computed } from 'vue'

const props = defineProps({
  loading: Boolean,
  error: String,
  reply: String,
  rows: { type: Array, default: null },
  title: { type: String, default: '查询结果' }
})

const LABELS = {
  departure_city: '出发',
  arrival_city: '到达',
  departure_time: '出发时间',
  arrival_time: '到达时间',
  train_number: '车次',
  seat_type: '席别',
  price: '票价',
  remaining_seats: '余票',
  flight_number: '航班',
  cabin_type: '舱位',
  artist: '艺人',
  venue: '场地',
  start_time: '开始时间',
  end_time: '结束时间',
  ticket_type: '票类',
  city: '城市',
  fx_date: '日期',
  text_day: '白天',
  text_night: '夜间',
  temp_max: '最高温',
  temp_min: '最低温',
  humidity: '湿度',
  wind_dir_day: '风向',
  precip: '降水',
  hotel_name: '酒店',
  district: '区域',
  room_type: '房型',
  bed_type: '床型',
  remaining_rooms: '余房',
  rating: '评分',
  has_breakfast: '早餐',
  has_wifi: 'WiFi',
  has_parking: '停车',
  day: '天数',
  date: '日期',
  weather: '天气',
  transport: '交通',
  hotel: '住宿',
  attractions: '景点'
}

const columns = computed(() => (props.rows && props.rows.length ? Object.keys(props.rows[0]) : []))

function label(key) {
  return LABELS[key] || key
}

function cell(row, key) {
  const value = row[key]
  if (key === 'has_breakfast' || key === 'has_wifi' || key === 'has_parking') {
    return value ? '有' : '无'
  }
  if (typeof value === 'string' && /^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$/.test(value)) {
    return value.slice(0, 16)
  }
  return value
}
</script>

<template>
  <section class="panel result-panel">
    <header class="panel-header">
      <h2>{{ title }}</h2>
      <span v-if="loading" class="status-badge loading">处理中</span>
      <span v-else-if="reply || (rows && rows.length)" class="status-badge ok">完成</span>
      <span v-else class="status-badge idle">待查询</span>
    </header>
    <div v-if="loading" class="result-body">
      <span class="spinner"></span>
    </div>
    <p v-else-if="error" class="error-text">{{ error }}</p>
    <table v-else-if="rows && rows.length" class="result-table">
      <thead>
        <tr>
          <th v-for="col in columns" :key="col">{{ label(col) }}</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="(row, i) in rows" :key="i">
          <td v-for="col in columns" :key="col">{{ cell(row, col) }}</td>
        </tr>
      </tbody>
    </table>
    <pre v-else-if="reply" class="result-text">{{ reply }}</pre>
    <p v-else class="empty-text">提交查询后，结果会显示在这里。</p>
  </section>
</template>

<style scoped>
.result-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}
.result-table th,
.result-table td {
  border: 1px solid var(--border);
  padding: 6px 8px;
  text-align: left;
  white-space: nowrap;
}
.result-table th {
  background: var(--panel-alt);
  color: var(--muted);
  font-weight: 600;
}
.result-table tbody tr:hover {
  background: var(--panel-alt);
}
</style>
