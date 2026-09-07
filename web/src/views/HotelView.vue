<script setup>
import { computed, ref } from 'vue'
import CitySelect from '../components/CitySelect.vue'
import Icon from '../components/Icon.vue'
import { setAuth } from '../auth'
import { bookHotel, demoLogin, getHotelRooms, searchHotels } from '../api'

function nextDay() {
  const day = new Date(Date.now() + 86400000)
  const pad = (n) => String(n).padStart(2, '0')
  return `${day.getFullYear()}-${pad(day.getMonth() + 1)}-${pad(day.getDate())}`
}

function addDays(base, count) {
  const day = new Date(base)
  day.setDate(day.getDate() + count)
  const pad = (n) => String(n).padStart(2, '0')
  return `${day.getFullYear()}-${pad(day.getMonth() + 1)}-${pad(day.getDate())}`
}

const city = ref('杭州')
const district = ref('')
const keyword = ref('')
const checkIn = ref(nextDay())
const nights = ref(1)
const rooms = ref(1)
const adults = ref(2)
const budget = ref('')
const guestName = ref('')
const contactPhone = ref('')

const loading = ref(false)
const roomLoading = ref(false)
const booking = ref(false)
const rows = ref([])
const roomRows = ref([])
const selectedHotel = ref(null)
const selectedRoom = ref(null)
const source = ref('')
const degraded = ref(false)
const message = ref('')
const error = ref('')
const orderResult = ref(null)

const totalPrice = computed(() => {
  const price = Number(selectedRoom.value?.price ?? selectedHotel.value?.price ?? 0)
  return Math.round(price * Number(nights.value || 1) * Number(rooms.value || 1) * 100) / 100
})

const checkOut = computed(() => addDays(checkIn.value, Number(nights.value || 1)))

async function ensureDemoLogin() {
  const data = await demoLogin()
  if (data && data.username) setAuth(data.username)
}

async function search() {
  error.value = ''
  message.value = ''
  orderResult.value = null
  roomRows.value = []
  selectedHotel.value = null
  selectedRoom.value = null
  if (!city.value) {
    error.value = '请选择城市'
    return
  }
  if (!checkIn.value) {
    error.value = '请选择入住日期'
    return
  }
  loading.value = true
  try {
    const data = await searchHotels({
      city: city.value,
      district: district.value || null,
      keyword: keyword.value || null,
      check_in: checkIn.value,
      nights: Number(nights.value || 1),
      adults: Number(adults.value || 2),
      budget: budget.value ? Number(budget.value) : null,
    })
    rows.value = data.rows || []
    source.value = data.source || ''
    degraded.value = Boolean(data.degraded)
    if (data.message) message.value = data.message
    if (!rows.value.length) message.value = message.value || '暂无酒店，请更换城市或日期。'
  } catch (e) {
    error.value = e.message
    rows.value = []
  } finally {
    loading.value = false
  }
}

async function chooseHotel(hotel) {
  error.value = ''
  orderResult.value = null
  selectedHotel.value = hotel
  selectedRoom.value = null
  roomRows.value = []
  if (!hotel.needs_room_detail) {
    selectedRoom.value = hotel
    return
  }
  roomLoading.value = true
  try {
    const data = await getHotelRooms({
      hotel,
      check_in: checkIn.value,
      nights: Number(nights.value || 1),
      adults: Number(adults.value || 2),
      rooms: Number(rooms.value || 1),
    })
    roomRows.value = data.rows || []
    message.value = data.message || ''
    if (!roomRows.value.length && !message.value) {
      message.value = '该酒店当前日期没有可售房型，请更换日期。'
    }
  } catch (e) {
    error.value = e.message
  } finally {
    roomLoading.value = false
  }
}

function chooseRoom(room) {
  selectedRoom.value = room
  orderResult.value = null
}

function fmtPrice(value) {
  const num = Number(value)
  return Number.isFinite(num) ? num.toFixed(num % 1 === 0 ? 0 : 2) : '--'
}

async function placeOrder() {
  error.value = ''
  orderResult.value = null
  const room = selectedRoom.value
  if (!selectedHotel.value || !room) {
    error.value = '请先选择酒店和可售房型'
    return
  }
  if (!guestName.value.trim() || !contactPhone.value.trim()) {
    error.value = '请填写演示入住人姓名和联系电话'
    return
  }
  booking.value = true
  try {
    await ensureDemoLogin()
    orderResult.value = await bookHotel({
      hotel: selectedHotel.value,
      room,
      check_in: checkIn.value,
      nights: Number(nights.value || 1),
      rooms: Number(rooms.value || 1),
      guest_name: guestName.value.trim(),
      contact_phone: contactPhone.value.trim(),
    })
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
        <h1>酒店</h1>
        <p class="muted">RollingGo 真实酒店搜索 · 房型实时比价 · 沙箱虚拟预订</p>
      </div>
      <span class="status-badge ok">沙箱模式</span>
    </header>

    <section class="panel">
      <div class="form-grid hotel-search-grid">
        <CitySelect v-model="city" />
        <label class="field-label">入住日期<input v-model="checkIn" type="date" class="text-input" /></label>
        <label class="field-label">晚数
          <select v-model.number="nights" class="select-input">
            <option v-for="n in 7" :key="n" :value="n">{{ n }} 晚</option>
          </select>
        </label>
        <label class="field-label">房间
          <select v-model.number="rooms" class="select-input">
            <option v-for="n in 4" :key="n" :value="n">{{ n }} 间</option>
          </select>
        </label>
        <label class="field-label">入住人数
          <input v-model.number="adults" type="number" min="1" max="8" class="text-input" />
        </label>
        <label class="field-label">区域/房型<input v-model="keyword" class="text-input" placeholder="如：西湖区、大床房" /></label>
        <label class="field-label">预算上限<input v-model.number="budget" type="number" min="1" class="text-input" placeholder="可选" /></label>
        <button class="primary-button" :disabled="loading" @click="search">
          <Icon name="search" :size="18" /> 搜索真实酒店
        </button>
      </div>
      <p class="hint-text">真实酒店来自 RollingGo 接口；预订只写入本地沙箱订单，不会产生真实扣款。</p>
    </section>

    <div v-if="error" class="banner error-banner"><Icon name="alert" :size="16" /> {{ error }}</div>
    <p v-if="message && !rows.length" class="hint-text">{{ message }}</p>

    <section v-if="rows.length || loading" class="panel">
      <header class="panel-header">
        <h2>{{ city }} 酒店 · {{ checkIn }} 起</h2>
        <div class="badge-row">
          <span v-if="loading" class="status-badge loading">搜索中</span>
          <span v-if="source && !loading" class="status-badge" :class="degraded ? 'loading' : 'ok'">{{ source }}</span>
        </div>
      </header>
      <div v-if="loading" class="result-body"><span class="spinner"></span></div>
      <div v-else class="hotel-grid">
        <article
          v-for="hotel in rows"
          :key="hotel._booking_key || hotel.hotel_name"
          class="hotel-card"
          :class="{ active: selectedHotel && selectedHotel._booking_key === hotel._booking_key }"
          @click="chooseHotel(hotel)"
        >
          <div class="hotel-card-main">
            <h3>{{ hotel.hotel_name }}</h3>
            <p class="muted">{{ hotel.address || `${hotel.city}${hotel.district || ''}` }}</p>
            <div class="hotel-tags">
              <span v-if="hotel.star_rating" class="mini-tag">{{ hotel.star_rating }} 星</span>
              <span v-if="hotel.room_type" class="mini-tag">{{ hotel.room_type }}</span>
              <span v-if="hotel.has_breakfast" class="mini-tag">含早</span>
              <span v-if="hotel.has_wifi" class="mini-tag">WiFi</span>
            </div>
          </div>
          <div class="hotel-price">
            <strong>¥{{ fmtPrice(hotel.price) }}</strong>
            <span>起/晚</span>
            <button class="secondary-button choose-btn" @click.stop="chooseHotel(hotel)">
              {{ hotel.needs_room_detail ? '查看房型' : '选择' }}
            </button>
          </div>
        </article>
      </div>
    </section>

    <section v-if="roomLoading || roomRows.length" class="panel">
      <header class="panel-header">
        <h2>{{ selectedHotel?.hotel_name }} · 可售房型</h2>
        <span v-if="roomLoading" class="status-badge loading">实时查价中</span>
        <span v-else class="status-badge ok">{{ checkIn }} 至 {{ checkOut }}</span>
      </header>
      <div v-if="roomLoading" class="result-body"><span class="spinner"></span></div>
      <div v-else class="room-list">
        <article
          v-for="room in roomRows"
          :key="room._booking_key || room.room_type + room.price"
          class="room-row"
          :class="{ active: selectedRoom && selectedRoom._booking_key === room._booking_key }"
          @click="chooseRoom(room)"
        >
          <div>
            <h3>{{ room.room_type }}</h3>
            <p class="muted">
              {{ room.bed_type || room.rate_plan_name }}
              <template v-if="room.room_size"> · {{ room.room_size }}㎡</template>
              <template v-if="room.meal_type"> · {{ room.meal_type }}</template>
            </p>
            <p class="muted">{{ room.cancel_policy || '' }}</p>
          </div>
          <div class="room-right">
            <strong>¥{{ fmtPrice(room.price) }}</strong>
            <span class="muted">/间/晚</span>
            <button class="secondary-button choose-btn" @click.stop="chooseRoom(room)">选择</button>
          </div>
        </article>
      </div>
    </section>

    <section v-if="selectedHotel && (selectedRoom || roomRows.length)" class="panel order-panel">
      <header class="panel-header">
        <h2>虚拟酒店预订确认</h2>
        <span class="status-badge loading">沙箱订单</span>
      </header>
      <div class="order-summary">
        <div>
          <span class="muted">酒店/房型</span>
          <strong>{{ selectedHotel.hotel_name }}</strong>
          <span>{{ selectedRoom?.room_type || '待选择房型' }}</span>
        </div>
        <div>
          <span class="muted">入离日期</span>
          <strong>{{ checkIn }} 入住</strong>
          <span>{{ checkOut }} 离店 · {{ nights }} 晚</span>
        </div>
        <div>
          <span class="muted">价格</span>
          <strong>¥{{ fmtPrice(selectedRoom?.price || selectedHotel.price) }} / 晚</strong>
          <span>{{ rooms }} 间 · {{ adults }} 位成人</span>
        </div>
      </div>
      <div v-if="selectedRoom" class="form-grid order-form">
        <label class="field-label">入住人姓名<input v-model="guestName" class="text-input" placeholder="如：张三" /></label>
        <label class="field-label">联系电话<input v-model="contactPhone" class="text-input" placeholder="演示用手机号" /></label>
        <div class="order-action">
          <strong class="total">合计 ¥{{ fmtPrice(totalPrice) }}</strong>
          <button class="primary-button" :disabled="booking" @click="placeOrder">
            <Icon name="bag" :size="18" /> {{ booking ? '提交中...' : '确认虚拟预订' }}
          </button>
        </div>
      </div>
    </section>

    <section v-if="orderResult" class="panel success-panel">
      <header class="panel-header">
        <h2>沙箱酒店订单已生成</h2>
        <span class="status-badge ok">confirmed</span>
      </header>
      <p class="success-line">
        订单号：{{ orderResult.order_no }}<br />
        金额：¥{{ fmtPrice(orderResult.total_price) }} · 晚数 {{ orderResult.nights }} · 房间 {{ orderResult.rooms }}
      </p>
      <p class="hint-text">订单只保存在项目本地，可在“订单”页查看并取消释放。</p>
    </section>
  </div>
</template>

<style scoped>
.hotel-search-grid {
  align-items: end;
}
.badge-row {
  display: flex;
  gap: 6px;
  align-items: center;
}
.hotel-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 12px;
}
.hotel-card {
  display: flex;
  justify-content: space-between;
  gap: 14px;
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 14px;
  cursor: pointer;
  transition: border-color 0.15s ease, background 0.15s ease;
}
.hotel-card:hover,
.hotel-card.active {
  border-color: var(--primary);
  background: rgba(15, 118, 110, 0.04);
}
.hotel-card-main h3 {
  margin: 0 0 4px;
  font-size: 15px;
}
.hotel-card-main p {
  font-size: 13px;
  line-height: 1.45;
}
.hotel-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 8px;
}
.mini-tag {
  font-size: 12px;
  color: var(--muted);
  border: 1px solid var(--line);
  border-radius: 999px;
  padding: 2px 8px;
}
.hotel-price {
  flex: 0 0 112px;
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 2px;
}
.hotel-price strong,
.room-right strong {
  color: var(--accent);
  font-size: 18px;
}
.hotel-price span,
.room-right span {
  color: var(--muted);
  font-size: 12px;
}
.choose-btn {
  height: 30px;
  margin-top: 8px;
  padding: 0 10px;
  font-size: 12px;
}
.room-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.room-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 12px 14px;
  cursor: pointer;
}
.room-row:hover,
.room-row.active {
  border-color: var(--primary);
  background: rgba(15, 118, 110, 0.05);
}
.room-row h3 {
  margin: 0 0 4px;
  font-size: 14px;
}
.room-row p {
  margin: 0;
  font-size: 12px;
  line-height: 1.5;
}
.room-right {
  display: flex;
  align-items: flex-end;
  flex-direction: column;
  gap: 2px;
}
.order-panel {
  display: flex;
  flex-direction: column;
  gap: 14px;
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
.order-summary span {
  color: var(--muted);
  font-size: 12px;
}
.order-action {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 12px;
}
.total {
  font-size: 16px;
}
.success-panel {
  border-color: #bbf7d0;
  background: #f6fdf8;
}
.success-line {
  line-height: 1.8;
  font-size: 14px;
}
</style>
