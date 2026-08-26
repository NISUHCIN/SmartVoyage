<script setup>
import { computed, onMounted, ref } from 'vue'
import { getCities } from '../api'

defineProps({
  modelValue: { type: String, default: '' }
})
const emit = defineEmits(['update:modelValue'])

const provinces = ref([])
const keyword = ref('')
const loading = ref(false)
const error = ref('')

onMounted(async () => {
  loading.value = true
  try {
    provinces.value = await getCities()
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
})

const filtered = computed(() => {
  const kw = keyword.value.trim()
  if (!kw) return provinces.value
  return provinces.value
    .map((p) => ({
      province: p.province,
      cities: p.cities.filter((c) => c.includes(kw) || p.province.includes(kw))
    }))
    .filter((p) => p.cities.length > 0)
})
</script>

<template>
  <div class="city-select">
    <label class="field-label">城市</label>
    <input v-model="keyword" class="text-input search-input" placeholder="输入城市名筛选" />
    <select class="select-input" :value="modelValue" @change="emit('update:modelValue', $event.target.value)">
      <option value="">请选择城市</option>
      <optgroup v-for="group in filtered" :key="group.province" :label="group.province">
        <option v-for="city in group.cities" :key="city" :value="city">{{ city }}</option>
      </optgroup>
    </select>
    <p v-if="error" class="error-text">{{ error }}</p>
    <p v-else-if="loading" class="hint-text">正在加载城市...</p>
  </div>
</template>

<style scoped>
.city-select {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.search-input {
  height: 34px;
}
</style>
