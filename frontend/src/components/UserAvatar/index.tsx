import { useEffect, useState } from 'react'
import { Image, Text, View } from '@tarojs/components'
import './index.scss'

interface Props {
  src?: string | null
  name: string
  className?: string
}

export default function UserAvatar({ src, name, className = '' }: Props) {
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    setFailed(false)
  }, [src])

  const showImage = Boolean(src) && !failed
  const initial = (name || '学习者').slice(0, 1)

  return (
    <View className={`user-avatar ${className}`}>
      {showImage ? (
        <Image
          className='user-avatar__img'
          src={src as string}
          mode='aspectFill'
          onError={() => setFailed(true)}
        />
      ) : (
        <Text className='user-avatar__text'>{initial}</Text>
      )}
    </View>
  )
}
