<script setup>
import { computed, onMounted, ref } from 'vue'
import { cancelOrder, getOrders } from '../api'
import Icon from '../components/Icon.vue'
import { clearAuth, getUsername } from '../auth'

const loggedIn = ref(Boolean(getUsername()))
const orders = ref([])
const loading = ref(false)
const error = ref('')
const cancelling = ref('')

const pendingCount = computed(() => orders.value.filter((o) => o.status === 'confirmed').length)

async function load() {
  loading.value = true
  error.value = ''
  try {
    orders.value = await getOrders()
  } catch (e) {
    error.value = e.message.includes('认证') || e.message.includes('401') ? '请先登录' : e.message
    if (error.value === '请先登录') {
      clearAuth()
      loggedIn.value = false
    }
  } finally {
    loading.value = false
  }
}

onMounted(load)

function itemOf(order) {
  if (order.item && typeof order.item === 'object') return order.item
  return {}
}

function fmtTime(value) {
  return value ? String(value).slice(0, 16).replace('T', ' ') : ''
}

function fmtDate(value) {
  return value ? String(value).slice(0, 10) : ''
}

function money(value) {
  const num = Number(value)
  if (!Number.isFinite(num)) return '--'
  return num.toFixed(num % 1 === 0 ? 0 : 2)
}

function cardView(order) {
  const item = itemOf(order)
  const mode = item.mode || (order.item_desc && order.item_desc.includes('virtual_demo') ? 'virtual_demo' : '')
  const base = {
    icon: order.order_type === 'hotel' ? 'bed' : 'ticket',
    title: '',
    subtitle: '',
    facts: [],
    mode,
    detailLines: [],
  }
  if (order.order_type === 'hotel') {
    base.title = item.hotel_name || item.hotel || '酒店订单'
    base.subtitle = `${item.city || ''} ${item.district || ''}`
    base.facts = [
      { label: '房型', value: item.room_type || item.room || '--' },
      { label: '入住', value: fmtDate(item.check_in) },
      { label: '离店', value: fmtDate(item.check_out) },
      { label: '间夜', value: `${item.rooms || order.quantity || 1}间 · ${item.nights || 1}晚` },
    ]
    if (item.bed_type) base.detailLines.push(`床型：${item.bed_type}`)
    if (item.meal_type) base.detailLines.push(`餐食：${item.meal_type}`)
    if (item.cancel_policy) base.detailLines.push(`退改：${item.cancel_policy}`)
    if (item.source) base.detailLines.push(`数据源：${item.source}`)
  } else if (order.order_type === 'train' || order.order_type === 'flight') {
    const departure = fmtTime(item.departure_time)
    const arrival = fmtTime(item.arrival_time)
    base.title = `${item.train_number || item.flight_number || '交通订单'} · ${item.seat_type || item.cabin_type || ''}`
    base.subtitle = `${item.departure_city || ''} → ${item.arrival_city || ''}`
    base.facts = [
      { label: '日期', value: fmtDate(item.travel_date || item.departure_time) },
      { label: '出发', value: departure },
      { label: '到达', value: arrival },
      { label: '乘客', value: order.contact_name || item.passenger_name || '--' },
    ]
    base.detailLines = [
      `票量：${order.quantity || 1} 张`,
      `联系电话：${order.contact_phone || item.contact_phone || '--'}`,
    ]
    if (item.source) base.detailLines.push(`数据源：${item.source}`)
  } else {
    base.title = order.order_type || '订单'
    base.subtitle = fmtDate(order.created_at)
    base.detailLines = [String(order.item_desc || '')]
  }
  return base
}

function statusText(status) {
  return { confirmed: '已确认', cancelled: '已取消', pending: '待确认' }[status] || status
}

async function cancel(orderNo) {
  cancelling.value = orderNo
  error.value = ''
  try {
    await cancelOrder(orderNo)
    await load()
  } catch (e) {
    error.value = e.message
  } finally {
    cancelling.value = ''
  }
}
</script>

<template>
  <div class="view">
    <header class="view-header">
      <div>
        <h1>订单</h1>
        <p class="muted">车次/日期/席别/乘客卡片视图，可取消沙箱订单释放占用</p>
      </div>
      <span v-if="pendingCount" class="status-badge ok">{{ pendingCount }} 个进行中</span>
    </header>

    <div v-if="!loggedIn" class="panel">
      <p class="empty-text">登录后查看订单</p>
      <router-link to="/auth" class="text-button"><Icon name="user" :size="16" /> 去登录</router-link>
    </div>
    <div v-else-if="error" class="panel">
      <p class="error-text">{{ error }}</p>
      <router-link v-if="error === '请先登录'" to="/auth" class="text-button"><Icon name="user" :size="16" /> 去登录</router-link>
    </div>
    <div v-else class="order-stack">
      <p v-if="loading" class="empty-text">正在加载订单...</p>
      <p v-else-if="orders.length === 0" class="empty-text">暂无订单，去票务或酒店页完成一次沙箱预订。</p>
      <article v-for="order in orders" :key="order.order_no" class="order-card panel">
        <div class="order-card-head">
          <div class="order-type-icon"><Icon :name="cardView(order).icon" :size="20" /></div>
          <div class="order-title">
            <h3>{{ cardView(order).title }}</h3>
            <p class="muted">{{ cardView(order).subtitle }}</p>
          </div>
          <div class="order-side">
            <span class="status-badge" :class="order.status === 'confirmed' ? 'ok' : 'idle'">
              {{ statusText(order.status) }}
            </span>
            <span v-if="cardView(order).mode === 'virtual_demo'" class="mini-badge">沙箱</span>
          </div>
        </div>
        <div class="order-facts">
          <div v-for="fact in cardView(order).facts" :key="fact.label" class="fact-cell">
            <span>{{ fact.label }}</span>
            <strong>{{ fact.value }}</strong>
          </div>
        </div>
        <p v-for="line in cardView(order).detailLines" :key="line" class="detail-line">{{ line }}</p>
        <div class="order-foot">
          <span class="order-no">订单号 {{ order.order_no }}</span>
          <span class="order-total">¥{{ money(order.total_price) }}</span>
          <button
            v-if="order.status === 'confirmed'"
            class="secondary-button danger-button"
            :disabled="cancelling === order.order_no"
            @click="cancel(order.order_no)"
          >
            <Icon name="refresh" :size="16" />
            {{ cancelling === order.order_no ? '取消中...' : '取消并释放' }}
          </button>
        </div>
      </article>
    </div>
  </div>
</template>

<style scoped>
.order-stack {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.order-card {
  padding: 16px;
}
.order-card-head {
  display: flex;
  align-items: flex-start;
  gap: 12px;
}
.order-type-icon {
  width: 40px;
  height: 40px;
  flex: 0 0 auto;
  border-radius: 8px;
  background: rgba(15, 118, 110, 0.12);
  color: var(--primary);
  display: grid;
  place-items: center;
}
.order-title {
  flex: 1;
  min-width: 0;
}
.order-title h3 {
  margin: 0 0 3px;
  font-size: 15px;
  overflow-wrap: anywhere;
}
.order-title p {
  font-size: 13px;
}
.order-side {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 6px;
}
.mini-badge {
  font-size: 11px;
  color: var(--accent);
  border: 1px solid #fde68a;
  background: #fffbeb;
  border-radius: 999px;
  padding: 2px 7px;
}
.order-facts {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
  gap: 10px;
  background: #f7f9fa;
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 12px;
  margin-top: 12px;
}
.fact-cell {
  display: flex;
  flex-direction: column;
  gap: 3px;
}
.fact-cell span {
  color: var(--muted);
  font-size: 12px;
}
.fact-cell strong {
  font-size: 13px;
}
.detail-line {
  margin: 8px 2px 0;
  color: var(--muted);
  font-size: 12px;
  line-height: 1.6;
}
.order-foot {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 14px;
  margin-top: 12px;
}
.order-no {
  color: var(--muted);
  font-size: 12px;
  margin-right: auto;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 46%;
}
.order-total {
  font-weight: 700;
  color: var(--accent);
}
.danger-button {
  color: var(--danger);
  border-color: #fecaca;
}
.danger-button:hover {
  border-color: var(--danger);
  color: var(--danger);
}
</style>
