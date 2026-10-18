import { View, Text } from '@tarojs/components'
import TabBar from '@/components/TabBar'
import './index.scss'

export default function Bank() {
  return (
    <View className='page'>
      <View className='ph-card'>
        <View className='ph-icon'>
          <View className='icon icon-book ph-icon__svg' />
        </View>
        <Text className='ph-title'>题库功能开发中</Text>
        <Text className='ph-desc'>
          导入资料生成题库、私有知识库、错题本等能力将在后续版本上线，敬请期待。
        </Text>
      </View>
      <TabBar active='bank' />
    </View>
  )
}
