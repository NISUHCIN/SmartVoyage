<script setup>
import { ref } from 'vue'
import { sendChat } from '../api'
import Icon from '../components/Icon.vue'

const sessionId = ref('web-' + Date.now().toString(36))
const input = ref('')
const loading = ref(false)
const messages = ref([
  { role: 'assistant', text: '你好，我是 SmartVoyage 旅行助手。' }
])

async function send() {
  const text = input.value.trim()
  if (!text || loading.value) return
  messages.value.push({ role: 'user', text })
  input.value = ''
  loading.value = true
  try {
    const data = await sendChat(text, sessionId.value)
    const reply = (data.reply || '').trim()
    messages.value.push({ role: 'assistant', text: reply || '未返回有效内容，请稍后重试。' })
  } catch (e) {
    messages.value.push({ role: 'assistant', text: '请求失败：' + e.message })
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="view">
    <header class="view-header">
      <h1>对话</h1>
      <p class="muted">自由输入需求，系统自动路由到对应 Agent</p>
    </header>
    <section class="panel chat-panel">
      <div class="chat-list">
        <div v-for="(msg, i) in messages" :key="i" class="chat-row">
          <div class="chat-label" :class="msg.role">{{ msg.role === 'user' ? '你' : 'AI 助手' }}</div>
          <div class="chat-msg" :class="msg.role">{{ msg.text }}</div>
        </div>
        <div v-if="loading" class="chat-msg assistant">
          <span class="spinner small"></span>
          <span class="loading-text">正在处理...</span>
        </div>
      </div>
      <div class="chat-input-row">
        <input
          v-model="input"
          class="text-input"
          placeholder="输入消息"
          @keydown.enter="send"
        />
        <button class="primary-button" :disabled="loading" @click="send"><Icon name="send" :size="18" /></button>
      </div>
    </section>
  </div>
</template>

<style scoped>
.chat-row {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.chat-label {
  font-size: 12px;
  color: var(--muted);
  padding: 0 4px;
}
.chat-label.user {
  align-self: flex-end;
}

.spinner.small {
  width: 18px;
  height: 18px;
  border-width: 2px;
}

.loading-text {
  color: var(--muted);
  font-size: 13px;
}
</style>
