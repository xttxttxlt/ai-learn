import { View, Text } from '@tarojs/components'
import TabBar from '@/components/TabBar'
import './index.scss'

export default function Profile() {
  return (
    <View className='page'>
      <View className='ph-card'>
        <View className='ph-icon'>
          <View className='icon icon-tab-profile-active ph-icon__svg' />
        </View>
        <Text className='ph-title'>个人中心开发中</Text>
        <Text className='ph-desc'>
          学习数据看板、微信登录、成就勋章与设置等能力将在后续版本上线，敬请期待。
        </Text>
      </View>
      <TabBar active='profile' />
    </View>
  )
}
