import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import QueryResult from '../components/QueryResult.vue'

describe('QueryResult', () => {
  it('renders structured rows with Chinese labels', () => {
    const wrapper = mount(QueryResult, {
      props: {
        rows: [{ train_number: 'G100', price: 553.5 }],
        reply: '',
        title: '车票'
      }
    })
    expect(wrapper.text()).toContain('车票')
    expect(wrapper.text()).toContain('车次')
    expect(wrapper.text()).toContain('G100')
    expect(wrapper.text()).toContain('票价')
  })
})
