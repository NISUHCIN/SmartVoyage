<script setup>
import { onMounted, ref } from 'vue'
import { cancelOrder, getOrders } from '../api'
import Icon from '../components/Icon.vue'
import { clearAuth, getUsername } from '../auth'

const loggedIn = ref(Boolean(getUsername()))
const orders = ref([])
const loading = ref(false)
const error = ref('')

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

async function cancel(orderNo) {
  try {
    await cancelOrder(orderNo)
    await load()
  } catch (e) {
    error.value = e.message
  }
}
</script>

<template>
  <div class="view">
    <header class="view-header">
      <h1>订单</h1>
      <p class="muted">查看和取消已预订的票务或酒店</p>
    </header>
    <div v-if="!loggedIn" class="panel">
      <p class="empty-text">登录后查看订单</p>
      <router-link to="/auth" class="text-button"><Icon name="user" :size="16" /> 去登录</router-link>
    </div>
    <div v-else-if="error" class="panel">
      <p class="error-text">{{ error }}</p>
      <router-link v-if="error === '请先登录'" to="/auth" class="text-button"><Icon name="user" :size="16" /> 去登录</router-link>
    </div>
    <section v-else class="panel">
      <p v-if="loading" class="empty-text">正在加载订单...</p>
      <p v-else-if="orders.length === 0" class="empty-text">暂无订单</p>
      <table v-else class="orders-table">
        <thead>
          <tr>
            <th>订单号</th>
            <th>类型</th>
            <th>内容</th>
            <th>状态</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="order in orders" :key="order.order_no">
            <td>{{ order.order_no }}</td>
            <td>{{ order.order_type }}</td>
            <td>{{ order.item_desc }}</td>
            <td>{{ order.status }}</td>
            <td>
              <button v-if="order.status === 'confirmed'" class="secondary-button" @click="cancel(order.order_no)">取消</button>
            </td>
          </tr>
        </tbody>
      </table>
    </section>
  </div>
</template>
