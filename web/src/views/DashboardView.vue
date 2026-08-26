<script setup>
import { computed, onMounted, ref } from 'vue'
import { getAgents, getCities } from '../api'
import Icon from '../components/Icon.vue'

const agents = ref([])
const cityCount = ref(0)
const loading = ref(true)
const error = ref('')

onMounted(async () => {
  try {
    const [agentData, cityData] = await Promise.all([getAgents(), getCities()])
    agents.value = agentData
    cityCount.value = cityData.reduce((n, p) => n + p.cities.length, 0)
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
})

const onlineCount = computed(() => agents.value.filter((a) => a.status === 'online').length)

const services = [
  { name: '天气', desc: '全国城市天气查询', icon: 'weather', to: '/weather' },
  { name: '票务', desc: '火车/高铁查询与订票', icon: 'ticket', to: '/ticket' },
  { name: '酒店', desc: '按城市与区域查找酒店', icon: 'bed', to: '/hotel' },
  { name: '行程', desc: '多日行程规划安排', icon: 'route', to: '/itinerary' }
]
</script>

<template>
  <div class="view">
    <header class="view-header">
      <div>
        <h1>SmartVoyage 旅行智能助手</h1>
        <p class="muted">多 Agent 协作的全国旅行规划工作台</p>
      </div>
      <div class="status-chips">
        <span class="chip"><Icon name="pin" :size="16" /> {{ cityCount }} 个城市</span>
        <span class="chip"><Icon name="wifi" :size="16" /> {{ onlineCount }} 个 Agent 在线</span>
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
