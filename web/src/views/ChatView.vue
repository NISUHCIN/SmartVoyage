<script setup>
import { computed, onMounted, ref } from 'vue'
import { createSession, getMessages, getSessions, getSessionMemory, sendChatStream } from '../api'
import Icon from '../components/Icon.vue'
import { getUsername } from '../auth'

const sessionId = ref(localStorage.getItem('sv_session_id') || '')
const sessions = ref([])
const activeTitle = ref('新对话')
const input = ref('')
const loading = ref(false)
const memoryChips = ref([])
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
  const memoryKey = 'sv_memory_' + sid
  const storedMemory = localStorage.getItem(memoryKey)
  if (storedMemory) {
    try {
      memoryChips.value = JSON.parse(storedMemory)
    } catch {
      memoryChips.value = []
    }
  } else {
    memoryChips.value = []
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
    const memory = await getSessionMemory(sid).catch(() => null)
    memoryChips.value = memory && memory.chips ? memory.chips : []
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
  memoryChips.value = []
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
    let latestTrace = null
    const result = await sendChatStream(text, sessionId.value, (delta) => {
      assistantMsg.text += delta
    }, (event) => {
      if (event.trace) latestTrace = event.trace
      if (event.chips) memoryChips.value = event.chips
    })
    if (result.session_id) rememberSession(result.session_id)
    assistantMsg.trace = latestTrace
    if (!assistantMsg.text.trim()) {
      assistantMsg.text = '未返回有效内容，请稍后重试。'
    }
    if (sessionId.value.startsWith('web-')) {
      localStorage.setItem(localHistoryKey(sessionId.value), JSON.stringify(messages.value))
      localStorage.setItem('sv_memory_' + sessionId.value, JSON.stringify(memoryChips.value))
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
    <section v-if="memoryChips.length" class="memory-panel">
      <span class="memory-label"><Icon name="pin" :size="15" /> 系统记住</span>
      <span v-for="chip in memoryChips" :key="chip.key" class="memory-chip">{{ chip.label }}</span>
    </section>
    <section class="panel chat-panel">
      <div class="chat-list">
        <div v-for="(msg, i) in messages" :key="i" class="chat-row">
          <div class="chat-label" :class="msg.role">{{ msg.role === 'user' ? '你' : 'AI 助手' }}</div>
          <div class="chat-msg" :class="msg.role">{{ msg.text }}</div>
          <div v-if="msg.trace && msg.trace.steps" class="trace-block">
            <div class="trace-head">
              <Icon name="route" :size="15" />
              <strong>执行轨迹</strong>
              <span v-if="msg.trace.intents" class="trace-intent">意图：{{ msg.trace.intents }}</span>
              <span class="trace-time">{{ msg.trace.duration_ms || 0 }}ms</span>
            </div>
            <div v-for="(step, si) in msg.trace.steps" :key="si" class="trace-row">
              <span class="trace-dot" :class="step.status === 'error' ? 'error' : 'ok'"></span>
              <span class="trace-step">{{ step.step }}</span>
              <span class="trace-agent">{{ step.agent }}</span>
              <span class="trace-source" :class="step.degraded ? 'degraded' : ''">
                {{ step.source || 'A2A Agent' }}
              </span>
              <span class="trace-duration">{{ step.duration_ms || 0 }}ms</span>
              <span v-if="step.degraded" class="degraded-badge">降级</span>
            </div>
          </div>
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

.memory-panel {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  background: #fbfcfd;
  border: 1px dashed #b7d2cf;
  border-radius: 8px;
  padding: 9px 12px;
}
.memory-label {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  color: var(--primary);
  font-size: 13px;
  font-weight: 600;
}
.memory-chip {
  border: 1px solid var(--line);
  border-radius: 999px;
  background: #fff;
  color: var(--muted);
  padding: 3px 10px;
  font-size: 12px;
}
.trace-block {
  width: 100%;
  max-width: 720px;
  align-self: flex-start;
  background: #f8fafb;
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 8px 10px;
  display: flex;
  flex-direction: column;
  gap: 5px;
  margin-top: 2px;
}
.trace-head {
  display: flex;
  align-items: center;
  gap: 7px;
  font-size: 12px;
  color: var(--muted);
}
.trace-head strong {
  color: var(--ink);
}
.trace-intent {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.trace-time {
  margin-left: auto;
  color: var(--muted);
}
.trace-row {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: var(--muted);
  flex-wrap: wrap;
}
.trace-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  flex: 0 0 auto;
  background: #d1d5db;
}
.trace-dot.ok {
  background: #16a34a;
}
.trace-dot.error {
  background: var(--danger);
}
.trace-step {
  color: var(--ink);
  font-weight: 600;
  white-space: nowrap;
}
.trace-agent {
  white-space: nowrap;
}
.trace-source {
  white-space: nowrap;
  color: #15803d;
}
.trace-source.degraded {
  color: var(--accent);
}
.trace-duration {
  margin-left: auto;
  white-space: nowrap;
}
.degraded-badge {
  border: 1px solid #fde68a;
  color: var(--accent);
  background: #fffbeb;
  border-radius: 999px;
  padding: 0 7px;
  font-size: 11px;
}
.chat-panel {
  min-height: 520px;
}
@media (max-width: 720px) {
  .trace-intent {
    flex-basis: 100%;
  }
}
</style>
