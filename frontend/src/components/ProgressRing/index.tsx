import { View, Text } from '@tarojs/components'
import './index.scss'

interface Props {
  percent: number
  size?: 'sm' | 'lg'
  color?: string
  label?: string
}

export default function ProgressRing({ percent, size = 'sm', color = '#ff7a2f', label }: Props) {
  const p = Math.max(0, Math.min(100, Math.round(percent)))
  const c = color
  return (
    <View
      className={`ring ring--${size}`}
      style={{ background: `conic-gradient(${c} 0 ${p}%, #ece7de ${p}% 100%)` }}
    >
      <View className='ring__inner' />
      <Text className='ring__label' style={{ color: c }}>
        {label ?? `${p}%`}
      </Text>
    </View>
  )
}
