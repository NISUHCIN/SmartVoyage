<script setup>
import { computed, onMounted, ref } from 'vue'
import { createSession, getMessages, getSessions, sendChatStream } from '../api'
import Icon from '../components/Icon.vue'
import { getUsername } from '../auth'

const sessionId = ref(localStorage.getItem('sv_session_id') || '')
const sessions = ref([])
const activeTitle = ref('新对话')
const input = ref('')
const loading = ref(false)
const messages = ref([
  { role: 'assistant', text: '你好，我是 SmartVoyage 旅行助手。' }
])
const welcome = { role: 'assistant', text: '你好，我是 SmartVoyage 旅行助手。' }

function localHistoryKey(sid) {
  return 'sv_messages_' + sid
}

function loadLocalHistory(sid) {
  const stored = localStorage.getItem(localHistoryKey(sid))
  if (stored) {
    try {
      messages.value = JSON.parse(stored)
    } catch {
      messages.value = [welcome]
    }
  } else {
    messages.value = [welcome]
  }
  activeTitle.value = '新对话'
}

const loggedIn = computed(() => Boolean(getUsername()))

async function refreshSessions() {
  if (!loggedIn.value) return
  try {
    sessions.value = await getSessions()
  } catch (e) {
    sessions.value = []
  }
}

async function loadMessages(sid) {
  try {
    const rows = await getMessages(sid)
    const loaded = rows.map((row) => ({ role: row.role, text: row.content }))
    messages.value = loaded.length ? loaded : [welcome]
    const found = sessions.value.find((s) => s.session_id === sid)
    activeTitle.value = found ? found.title : '新对话'
  } catch (e) {
    loadLocalHistory(sid)
  }
}

function rememberSession(sid) {
  sessionId.value = sid
  localStorage.setItem('sv_session_id', sid)
}

function chooseSession(sid) {
  if (loading.value) return
  rememberSession(sid)
  loadMessages(sid)
}

async function newChat() {
  if (loading.value) return
  messages.value = [welcome]
  const oldSid = sessionId.value
  sessionId.value = ''
  activeTitle.value = '新对话'
  localStorage.removeItem('sv_session_id')
  if (oldSid) localStorage.removeItem(localHistoryKey(oldSid))
  if (loggedIn.value) {
    try {
      const data = await createSession('新对话')
      rememberSession(data.session_id)
      await refreshSessions()
    } catch (e) {
      // 创建失败时退化为本地会话
    }
  }
}

async function ensureSession() {
  if (sessionId.value) return
  if (loggedIn.value) {
    const data = await createSession('新对话')
    rememberSession(data.session_id)
    await refreshSessions()
  } else {
    rememberSession('web-' + Date.now().toString(36))
  }
}

onMounted(async () => {
  await refreshSessions()
  if (sessionId.value) {
    if (sessionId.value.startsWith('web-')) {
      loadLocalHistory(sessionId.value)
    } else {
      await loadMessages(sessionId.value)
    }
  } else if (loggedIn.value && sessions.value.length) {
    rememberSession(sessions.value[0].session_id)
    await loadMessages(sessions.value[0].session_id)
  }
})

async function send() {
  const text = input.value.trim()
  if (!text || loading.value) return
  try {
    await ensureSession()
  } catch (e) {
    messages.value.push({ role: 'assistant', text: '创建会话失败：' + e.message })
    return
  }

  messages.value.push({ role: 'user', text })
  const assistantMsg = { role: 'assistant', text: '' }
  messages.value.push(assistantMsg)
  input.value = ''
  loading.value = true
  try {
    const result = await sendChatStream(text, sessionId.value, (delta) => {
      assistantMsg.text += delta
    })
    if (result.session_id) rememberSession(result.session_id)
    if (!assistantMsg.text.trim()) {
      assistantMsg.text = '未返回有效内容，请稍后重试。'
    }
    if (sessionId.value.startsWith('web-')) {
      localStorage.setItem(localHistoryKey(sessionId.value), JSON.stringify(messages.value))
    }
  } catch (e) {
    assistantMsg.text = '请求失败：' + e.message
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="view">
    <header class="view-header">
      <div>
        <h1>对话</h1>
        <p class="muted">自由输入需求，系统自动路由到对应 Agent</p>
      </div>
      <div class="chat-actions">
        <select
          v-if="loggedIn && sessions.length"
          class="select-input session-select"
          :value="sessionId"
          @change="chooseSession($event.target.value)"
        >
          <option v-for="s in sessions" :key="s.session_id" :value="s.session_id">
            {{ s.title || '新对话' }}
          </option>
        </select>
        <button class="secondary-button" :disabled="loading" @click="newChat">
          <Icon name="refresh" :size="18" /> 新建对话
        </button>
      </div>
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
.chat-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}
.session-select {
  min-width: 140px;
  max-width: 220px;
}
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
