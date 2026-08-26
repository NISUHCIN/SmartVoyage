<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { login, register } from '../api'
import Icon from '../components/Icon.vue'
import { setAuth } from '../auth'

const router = useRouter()
const tab = ref('login')
const username = ref('')
const password = ref('')
const email = ref('')
const phone = ref('')
const error = ref('')
const loading = ref(false)

function saveAuth(data) {
  setAuth(data.username || username.value)
  router.push('/orders')
}

async function submit() {
  error.value = ''
  loading.value = true
  try {
    if (tab.value === 'login') {
      const data = await login(username.value, password.value)
      saveAuth(data)
    } else {
      const data = await register({
        username: username.value,
        password: password.value,
        email: email.value || null,
        phone: phone.value || null
      })
      saveAuth(data)
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
    <section class="panel auth-card">
      <div class="segmented auth-tabs">
        <button :class="{ active: tab === 'login' }" @click="tab = 'login'">登录</button>
        <button :class="{ active: tab === 'register' }" @click="tab = 'register'">注册</button>
      </div>
      <form class="auth-form" @submit.prevent="submit">
        <label class="field-label">用户名<input v-model="username" class="text-input" required /></label>
        <label class="field-label">密码<input v-model="password" type="password" class="text-input" required /></label>
        <template v-if="tab === 'register'">
          <label class="field-label">邮箱<input v-model="email" class="text-input" /></label>
          <label class="field-label">手机号<input v-model="phone" class="text-input" /></label>
        </template>
        <p v-if="error" class="error-text">{{ error }}</p>
        <button class="primary-button" :disabled="loading">
          <Icon :name="tab === 'login' ? 'user' : 'check'" :size="18" />
          {{ tab === 'login' ? '登录' : '注册' }}
        </button>
      </form>
    </section>
  </div>
</template>

<style scoped>
.auth-tabs {
  margin-bottom: 18px;
}
.auth-card {
  max-width: 420px;
}
</style>
