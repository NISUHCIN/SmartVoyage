<script setup>
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import Icon from './components/Icon.vue'

const route = useRoute()
const router = useRouter()
const username = computed(() => localStorage.getItem('sv_username') || '')
const loggedIn = computed(() => Boolean(localStorage.getItem('sv_token')))

const nav = [
  { to: '/', label: '工作台', icon: 'dashboard' },
  { to: '/weather', label: '天气', icon: 'weather' },
  { to: '/ticket', label: '票务', icon: 'ticket' },
  { to: '/hotel', label: '酒店', icon: 'bed' },
  { to: '/itinerary', label: '行程', icon: 'route' },
  { to: '/chat', label: '对话', icon: 'chat' },
  { to: '/orders', label: '订单', icon: 'bag' }
]

function logout() {
  localStorage.removeItem('sv_token')
  localStorage.removeItem('sv_username')
  router.push('/')
}
</script>

<template>
  <div class="app-shell">
    <aside class="sidebar">
      <div class="brand">
        <span class="brand-mark"><Icon name="sparkles" :size="20" /></span>
        <div>
          <strong>SmartVoyage</strong>
          <span>A2A 旅行助手</span>
        </div>
      </div>
      <nav class="nav-list">
        <router-link
          v-for="item in nav"
          :key="item.to"
          :to="item.to"
          class="nav-item"
          :class="{ active: route.path === item.to }"
        >
          <Icon :name="item.icon" :size="18" />
          <span>{{ item.label }}</span>
        </router-link>
      </nav>
    </aside>
    <div class="main">
      <header class="topbar">
        <div class="topbar-title">{{ route.meta.title || 'SmartVoyage' }}</div>
        <div class="user-area">
          <template v-if="loggedIn">
            <span class="user-chip"><Icon name="user" :size="16" /> {{ username }}</span>
            <button class="icon-button" title="退出登录" @click="logout">
              <Icon name="logout" :size="18" />
            </button>
          </template>
          <router-link v-else to="/auth" class="text-button">
            <Icon name="user" :size="16" /> 登录
          </router-link>
        </div>
      </header>
      <main class="content">
        <router-view />
      </main>
    </div>
  </div>
</template>
