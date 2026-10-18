import { View, Text } from '@tarojs/components'
import Taro from '@tarojs/taro'
import './index.scss'

export type TabKey = 'home' | 'bank' | 'profile'

const TABS: { key: TabKey; label: string; url: string }[] = [
  { key: 'home', label: '闯关', url: '/pages/index/index' },
  { key: 'bank', label: '题库', url: '/pages/bank/index' },
  { key: 'profile', label: '我的', url: '/pages/profile/index' }
]

export default function TabBar({ active }: { active: TabKey }) {
  const go = (url: string) => {
    Taro.reLaunch({ url })
  }

  return (
    <View className='tabbar'>
      {TABS.map(t => {
        const on = t.key === active
        return (
          <View
            key={t.key}
            className={`tab ${on ? 'tab--active' : ''}`}
            onClick={() => go(t.url)}
          >
            <View className={`icon tab__icon icon-tab-${t.key}${on ? '-active' : ''}`} />
            <Text className='tab__label'>{t.label}</Text>
          </View>
        )
      })}
    </View>
  )
}
