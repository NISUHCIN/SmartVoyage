import { createRouter, createWebHashHistory } from 'vue-router'
import DashboardView from './views/DashboardView.vue'
import WeatherView from './views/WeatherView.vue'
import TicketView from './views/TicketView.vue'
import HotelView from './views/HotelView.vue'
import ItineraryView from './views/ItineraryView.vue'
import ChatView from './views/ChatView.vue'
import AuthView from './views/AuthView.vue'
import OrdersView from './views/OrdersView.vue'

const routes = [
  { path: '/', component: DashboardView, meta: { title: '工作台' } },
  { path: '/weather', component: WeatherView, meta: { title: '天气查询' } },
  { path: '/ticket', component: TicketView, meta: { title: '票务' } },
  { path: '/hotel', component: HotelView, meta: { title: '酒店' } },
  { path: '/itinerary', component: ItineraryView, meta: { title: '行程规划' } },
  { path: '/chat', component: ChatView, meta: { title: '对话' } },
  { path: '/orders', component: OrdersView, meta: { title: '订单' } },
  { path: '/auth', component: AuthView, meta: { title: '登录' } }
]

export default createRouter({
  history: createWebHashHistory(),
  routes
})
