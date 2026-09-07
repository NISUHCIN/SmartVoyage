<script setup>
import { computed, ref } from 'vue'
import CitySelect from '../components/CitySelect.vue'
import Icon from '../components/Icon.vue'
import { setAuth } from '../auth'
import { bookTrain, demoLogin, searchTrains } from '../api'

const fromCity = ref('上海')
const toCity = ref('杭州')
const seatType = ref('二等座')

function nextDay() {
  const day = new Date(Date.now() + 86400000)
  const pad = (n) => String(n).padStart(2, '0')
  return `${day.getFullYear()}-${pad(day.getMonth() + 1)}-${pad(day.getDate())}`
}

const date = ref(nextDay())
const quantity = ref(1)
const passengerName = ref('')
const contactPhone = ref('')
const loading = ref(false)
const booking = ref(false)
const rows = ref([])
const source = ref('')
const message = ref('')
const error = ref('')
const selected = ref(null)
const orderResult = ref(null)

const seatOptions = ['商务座', '一等座', '二等座', '软卧', '硬卧', '硬座', '无座']

const totalPrice = computed(() => {
  if (!selected.value) return 0
  return Math.round((Number(selected.value.price) || 0) * Number(quantity.value || 1) * 100) / 100
})

async function search() {
  error.value = ''
  message.value = ''
  orderResult.value = null
  if (!fromCity.value || !toCity.value || fromCity.value === toCity.value) {
    error.value = '请选择不同的出发和到达城市'
    return
  }
  if (!date.value) {
    error.value = '请选择乘车日期'
    return
  }
  loading.value = true
  try {
    const data = await searchTrains({
      departure_city: fromCity.value,
      arrival_city: toCity.value,
      travel_date: date.value,
      seat_type: seatType.value,
    })
    rows.value = data.rows || []
    source.value = data.source || ''
    selected.value = null
    if (!rows.value.length) {
      message.value = '暂无符合该条件的真实余票，可换日期、席别或车站后重试。'
    }
  } catch (e) {
    error.value = e.message
    rows.value = []
  } finally {
    loading.value = false
  }
}

function choose(row) {
  selected.value = row
  orderResult.value = null
}

function formatTime(value) {
  return value && value.length >= 16 ? value.slice(0, 16) : value
}

async function ensureDemoLogin() {
  const data = await demoLogin()
  if (data && data.username) setAuth(data.username)
}

async function placeOrder() {
  error.value = ''
  orderResult.value = null
  if (!selected.value) {
    error.value = '请先选择一个真实班次'
    return
  }
  if (!passengerName.value.trim() || !contactPhone.value.trim()) {
    error.value = '请填写演示乘客姓名和联系电话'
    return
  }
  booking.value = true
  try {
    await ensureDemoLogin()
    const key = selected.value._booking_key
    orderResult.value = await bookTrain({
      train: selected.value,
      passenger_name: passengerName.value.trim(),
      contact_phone: contactPhone.value.trim(),
      quantity: Number(quantity.value || 1),
    })
    await search()
    selected.value = rows.value.find((row) => row._booking_key === key) || selected.value
  } catch (e) {
    error.value = e.message
  } finally {
    booking.value = false
  }
}
</script>

<template>
  <div class="view">
    <header class="view-header">
      <div>
        <h1>火车票</h1>
        <p class="muted">聚美智数/12306 真实余票 · 虚拟订票演示</p>
      </div>
      <span class="status-badge ok">沙箱模式</span>
    </header>

    <section class="panel">
      <div class="form-grid ticket-grid">
        <CitySelect v-model="fromCity" />
        <CitySelect v-model="toCity" />
        <label class="field-label">日期<input v-model="date" type="date" class="text-input" /></label>
        <label class="field-label">席别
          <select v-model="seatType" class="select-input">
            <option v-for="seat in seatOptions" :key="seat" :value="seat">{{ seat }}</option>
          </select>
        </label>
        <button class="primary-button" :disabled="loading" @click="search">
          <Icon name="search" :size="18" /> 查询真实余票
        </button>
      </div>
      <p class="hint-text">真实班次与价格来自聚美智数/阿里云接口；下单仅写入本地沙箱，不会产生真实出票。</p>
    </section>

    <div v-if="error" class="banner error-banner"><Icon name="alert" :size="16" /> {{ error }}</div>
    <p v-if="message" class="hint-text">{{ message }}</p>

    <section v-if="rows.length || loading" class="panel result-panel">
      <header class="panel-header">
        <h2>{{ fromCity }} → {{ toCity }} · {{ date }}</h2>
        <span v-if="source" class="status-badge ok">{{ source }}</span>
        <span v-if="loading" class="status-badge loading">查询中</span>
      </header>
      <div class="table-wrap">
        <table class="train-table">
          <thead>
            <tr>
              <th>出发</th>
              <th>到达</th>
              <th>车次</th>
              <th>席别</th>
              <th>票价</th>
              <th>余票</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in rows" :key="row._booking_key || row.train_number + row.departure_time" :class="{ active: selected && selected._booking_key === row._booking_key }">
              <td>
                <strong>{{ row.departure_city }}</strong>
                <small>{{ formatTime(row.departure_time) }}</small>
              </td>
              <td>
                <strong>{{ row.arrival_city }}</strong>
                <small>{{ formatTime(row.arrival_time) }}</small>
              </td>
              <td>
                <strong>{{ row.train_number }}</strong>
                <small>{{ row.train_type }}</small>
              </td>
              <td>{{ row.seat_type }}</td>
              <td>¥{{ row.price }}</td>
              <td>
                <span v-if="row.remaining_seats !== null && row.remaining_seats !== undefined">
                  {{ row.remaining_seats }} 张
                </span>
                <span v-else>{{ row.remaining_text || '余票充足' }}</span>
                <em v-if="row.virtual_occupied" class="occupied">
                  本系统已占用 {{ row.virtual_occupied }}
                </em>
              </td>
              <td>
                <button class="secondary-button" :disabled="loading || booking" @click="choose(row)">
                  选择
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <section v-if="selected" class="panel order-panel">
      <header class="panel-header">
        <h2>虚拟订票确认</h2>
        <span class="status-badge loading">沙箱订单</span>
      </header>
      <div class="order-summary">
        <div>
          <span class="muted">车次</span>
          <strong>{{ selected.train_number }} {{ selected.seat_type }}</strong>
          <span>{{ selected.departure_city }} → {{ selected.arrival_city }}</span>
        </div>
        <div>
          <span class="muted">乘车时间</span>
          <strong>{{ formatTime(selected.departure_time) }} 开</strong>
          <span>{{ formatTime(selected.arrival_time) }} 到</span>
        </div>
        <div>
          <span class="muted">单价</span>
          <strong>¥{{ selected.price }}</strong>
          <span>虚拟订单，不产生真实出票</span>
        </div>
      </div>
      <div class="form-grid order-form">
        <label class="field-label">张数
          <input v-model.number="quantity" type="number" min="1" max="5" class="text-input" />
        </label>
        <label class="field-label">乘客姓名
          <input v-model="passengerName" class="text-input" placeholder="如：张三" />
        </label>
        <label class="field-label">联系电话
          <input v-model="contactPhone" class="text-input" placeholder="演示用手机号" />
        </label>
        <div class="order-action">
          <strong class="total">合计 ¥{{ totalPrice }}</strong>
          <button class="primary-button" :disabled="booking" @click="placeOrder">
            <Icon name="bag" :size="18" /> {{ booking ? '提交中...' : '确认虚拟订票' }}
          </button>
        </div>
      </div>
    </section>

    <section v-if="orderResult" class="panel success-panel">
      <header class="panel-header">
        <h2>沙箱订单已生成</h2>
        <span class="status-badge ok">confirmed</span>
      </header>
      <p class="success-line">
        订单号：{{ orderResult.order_no }}<br />
        金额：¥{{ orderResult.total_price }} · 模式：{{ orderResult.mode }}
      </p>
      <p class="hint-text">此订单只存在于项目本地数据库，真实余票查询下一轮会自动扣除本次占用。</p>
    </section>
  </div>
</template>

<style scoped>
.ticket-grid {
  align-items: end;
}
.table-wrap {
  overflow: auto;
  max-height: 460px;
}
.train-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}
.train-table th,
.train-table td {
  border-bottom: 1px solid var(--line);
  padding: 10px 12px;
  text-align: left;
  vertical-align: middle;
}
.train-table th {
  color: var(--muted);
  font-size: 12px;
  font-weight: 600;
  background: #f7f9fa;
  position: sticky;
  top: 0;
}
.train-table td strong,
.train-table td small {
  display: block;
}
.train-table td small {
  color: var(--muted);
  font-size: 12px;
  margin-top: 2px;
}
.train-table tr.active td {
  background: rgba(15, 118, 110, 0.08);
}
.occupied {
  display: block;
  margin-top: 3px;
  color: var(--accent);
  font-style: normal;
  font-size: 12px;
}
.order-panel {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.order-summary {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 12px;
}
.order-summary > div {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 12px;
  background: #f7f9fa;
  border: 1px solid var(--line);
  border-radius: 8px;
}
.order-form {
  margin-top: 4px;
}
.order-action {
  display: flex;
  align-items: center;
  gap: 12px;
  justify-content: flex-end;
}
.total {
  font-size: 16px;
}
.success-panel {
  border-color: #bbf7d0;
  background: #f6fdf8;
}
.success-line {
  font-size: 14px;
  line-height: 1.8;
}
</style>
