import { useState } from 'react'
import { View, Text } from '@tarojs/components'
import Taro, { useDidShow } from '@tarojs/taro'
import CoinPill from '@/components/CoinPill'
import ProgressRing from '@/components/ProgressRing'
import TabBar from '@/components/TabBar'
import { getProfile, getQuizHistory, updateProfile } from '@/services/api'
import { ensureLogin, setCachedUser } from '@/services/auth'
import { formatHistoryDate } from '@/store'
import type { QuizHistoryItem, UserProfile } from '@/types'
import './index.scss'

const SLOGAN = '把知识做成关卡，一关一关闯下去。'

export default function Profile() {
  const [profile, setProfile] = useState<UserProfile | null>(null)
  const [history, setHistory] = useState<QuizHistoryItem[]>([])
  const [loading, setLoading] = useState(true)

  const refresh = async () => {
    const logged = await ensureLogin()
    if (!logged) {
      setLoading(false)
      return
    }
    try {
      const [p, h] = await Promise.all([getProfile(), getQuizHistory(1, 20)])
      setProfile(p)
      setCachedUser({ id: p.id, nickname: p.nickname, avatar_url: p.avatar_url, total_coins: p.total_coins })
      setHistory(h.items)
    } catch (e) {
      // 静默失败，展示空态
    } finally {
      setLoading(false)
    }
  }

  useDidShow(() => {
    refresh()
  })

  const onEditNickname = async () => {
    // editable/placeholderText 是微信扩展字段，Taro 4.3 类型定义未收录
    const res = (await Taro.showModal({
      title: '修改昵称',
      editable: true,
      placeholderText: '输入新昵称（1-20 字）',
      confirmText: '保存',
      cancelText: '取消'
    } as unknown as Taro.showModal.Option)) as { confirm: boolean; content?: string }
    if (!res.confirm) return
    const nickname = (res.content || '').trim()
    if (!nickname || nickname.length > 20) {
      Taro.showToast({ title: '昵称需为 1-20 字', icon: 'none' })
      return
    }
    try {
      const p = await updateProfile({ nickname })
      setProfile(p)
      setCachedUser({ id: p.id, nickname: p.nickname, avatar_url: p.avatar_url, total_coins: p.total_coins })
      Taro.showToast({ title: '昵称已更新', icon: 'success' })
    } catch (e) {
      Taro.showToast({ title: '修改失败，请重试', icon: 'none' })
    }
  }

  const openHistory = (item: QuizHistoryItem) => {
    // 已完成 → 回看报告；未完成 → 断点续答
    if (item.accuracy !== null) {
      Taro.navigateTo({ url: `/pages/report/index?quiz_id=${item.quiz_id}` })
    } else {
      Taro.navigateTo({ url: `/pages/quiz/index?quiz_id=${item.quiz_id}` })
    }
  }

  const nickname = profile?.nickname || '学习者'

  return (
    <View className='page'>
      {/* 用户卡片 */}
      <View className='user-card'>
        <View className='user-card__avatar'>
          <Text>{nickname.slice(0, 1)}</Text>
        </View>
        <View className='user-card__info'>
          <View className='user-card__name-row' onClick={onEditNickname}>
            <Text className='user-card__name'>{nickname}</Text>
            <View className='user-card__edit'>
              <Text>修改</Text>
            </View>
          </View>
          <Text className='user-card__slogan'>{SLOGAN}</Text>
        </View>
        <CoinPill value={profile?.total_coins ?? 0} />
      </View>

      {/* 统计卡 */}
      <View className='stats-card'>
        <View className='stats-cell'>
          <Text className='stats-cell__num'>{profile?.quiz_count ?? 0}</Text>
          <Text className='stats-cell__label'>闯关次数</Text>
        </View>
        <View className='stats-cell'>
          <Text className='stats-cell__num'>{profile?.correct_count ?? 0}</Text>
          <Text className='stats-cell__label'>答对题数</Text>
        </View>
        <View className='stats-cell'>
          <Text className='stats-cell__num'>{profile?.average_accuracy ?? 0}%</Text>
          <Text className='stats-cell__label'>平均正确率</Text>
        </View>
      </View>

      {/* 闯关历史 */}
      <Text className='list-title'>闯关历史</Text>

      {loading ? (
        <View className='empty'>
          <Text>加载中…</Text>
        </View>
      ) : history.length === 0 ? (
        <View className='empty'>
          <Text>还没有闯关记录，先去闯一关吧～</Text>
        </View>
      ) : (
        history.map(item => (
          <View className='item' key={item.quiz_id} onClick={() => openHistory(item)}>
            <View className='item__avatar'>
              <View className='icon icon-book item__avatar-icon' />
            </View>
            <View className='item__body'>
              <Text className='item__title'>{item.title}</Text>
              <Text className='item__date'>{formatHistoryDate(item.created_at)}</Text>
            </View>
            {item.accuracy !== null ? (
              <ProgressRing
                percent={item.accuracy}
                size='sm'
                color={item.accuracy >= 50 ? '#ff7a2f' : '#47a4ff'}
              />
            ) : (
              <Text className='item__status'>
                {item.answered_count ? `已答 ${item.answered_count}/${item.question_count ?? ''}` : '未完成'}
              </Text>
            )}
          </View>
        ))
      )}

      <TabBar active='profile' />
    </View>
  )
}
