import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import CitySelect from '../components/CitySelect.vue'
import { getCities } from '../api'

vi.mock('../api', () => ({ getCities: vi.fn() }))

describe('CitySelect', () => {
  beforeEach(() => {
    getCities.mockReset()
    getCities.mockResolvedValue([
      { province: '北京', cities: ['北京', '朝阳'] },
      { province: '上海', cities: ['上海'] }
    ])
  })

  it('renders cities after load', async () => {
    const wrapper = mount(CitySelect, { props: { modelValue: '' } })
    await flushPromises()
    const options = wrapper.findAll('option').map((o) => o.text())
    expect(options).toEqual(expect.arrayContaining(['北京', '朝阳', '上海']))
  })

  it('filters cities by keyword and emits selection', async () => {
    const wrapper = mount(CitySelect, { props: { modelValue: '' } })
    await flushPromises()
    await wrapper.find('.search-input').setValue('上海')
    expect(wrapper.find('optgroup').attributes('label')).toBe('上海')
    await wrapper.find('select').setValue('上海')
    expect(wrapper.emitted('update:modelValue')[0]).toEqual(['上海'])
  })
})
