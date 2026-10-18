import { View, Text } from '@tarojs/components'
import './index.scss'

interface Props {
  value: number | string
  prefix?: string
}

export default function CoinPill({ value, prefix = '' }: Props) {
  return (
    <View className='coin-pill'>
      <Text className='coin-pill__num'>
        {prefix}
        {value}
      </Text>
      <View className='icon icon-coin coin-pill__icon' />
    </View>
  )
}
