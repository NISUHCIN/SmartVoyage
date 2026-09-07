<script setup>
import { computed, onMounted, ref } from 'vue'
import { getAgents, getCities, getDemoStatus } from '../api'
import Icon from '../components/Icon.vue'

const agents = ref([])
const cityCount = ref(0)
const loading = ref(true)
const error = ref('')
const demoStatus = ref(null)

onMounted(async () => {
  try {
    const [agentData, cityData, statusData] = await Promise.allSettled([
      getAgents(),
      getCities(),
      getDemoStatus(),
    ])
    if (agentData.status === 'fulfilled') agents.value = agentData.value
    if (cityData.status === 'fulfilled') {
      cityCount.value = cityData.value.reduce((n, p) => n + p.cities.length, 0)
    }
    if (statusData.status === 'fulfilled') demoStatus.value = statusData.value
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
})

const onlineCount = computed(() => agents.value.filter((a) => a.status === 'online').length)

const services = [
  { name: '天气', desc: '全国城市真实天气', icon: 'weather', to: '/weather' },
  { name: '票务', desc: '真实余票 → 选座 → 沙箱订单', icon: 'ticket', to: '/ticket' },
  { name: '酒店', desc: '真实酒店 → 房型 → 沙箱订单', icon: 'bed', to: '/hotel' },
  { name: '行程', desc: '真实数据结构化时间线', icon: 'route', to: '/itinerary' }
]
</script>

<template>
  <div class="view">
    <header class="view-header">
      <div>
        <h1>SmartVoyage 旅行智能助手</h1>
        <p class="muted">A2A 多 Agent 协作 · 真实搜索 · 沙箱预订 · 可观测执行轨迹</p>
      </div>
      <div class="status-chips">
        <span class="chip"><Icon name="pin" :size="16" /> {{ cityCount }} 个城市</span>
        <span class="chip"><Icon name="wifi" :size="16" /> {{ onlineCount }} 个 Agent 在线</span>
        <span class="chip" :class="{ error: demoStatus && demoStatus.db === false }">
          <Icon name="database" :size="16" />
          {{ demoStatus ? (demoStatus.db ? 'MySQL 在线' : 'MySQL 离线') : '检测中' }}
        </span>
      </div>
    </header>

    <div v-if="error" class="banner error-banner"><Icon name="alert" :size="16" /> {{ error }}</div>

    <section class="section">
      <h2>服务</h2>
      <div class="service-grid">
        <article v-for="svc in services" :key="svc.name" class="service-card">
          <div class="service-icon"><Icon :name="svc.icon" :size="22" /></div>
          <div>
            <h3>{{ svc.name }}</h3>
            <p>{{ svc.desc }}</p>
          </div>
          <router-link class="icon-button" :to="svc.to" title="进入服务"><Icon name="send" :size="18" /></router-link>
        </article>
      </div>
    </section>

    <section class="section">
      <h2>Agent 状态</h2>
      <div class="agent-list">
        <article v-for="agent in agents" :key="agent.name" class="agent-row">
          <span class="dot" :class="agent.status"></span>
          <div>
            <h3>{{ agent.name }}</h3>
            <p class="muted">{{ agent.url }}</p>
          </div>
          <span class="status-badge" :class="agent.status">{{ agent.status === 'online' ? '在线' : '离线' }}</span>
        </article>
        <p v-if="loading" class="empty-text">正在加载 Agent 状态...</p>
      </div>
    </section>
  </div>
</template>

<style scoped>
.chip.error {
  color: var(--danger);
  border-color: #fecaca;
  background: #fef2f2;
}
</style>
