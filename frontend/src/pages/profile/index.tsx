import { useState } from 'react'
import { Button, Input, Text, View } from '@tarojs/components'
import Taro, { useDidShow } from '@tarojs/taro'
import CoinPill from '@/components/CoinPill'
import ProgressRing from '@/components/ProgressRing'
import TabBar from '@/components/TabBar'
import UserAvatar from '@/components/UserAvatar'
import { getProfile, getQuizHistory, updateProfile, uploadAvatar } from '@/services/api'
import { ensureLogin, setCachedUser } from '@/services/auth'
import { ApiError } from '@/services/request'
import { formatHistoryDate } from '@/store'
import type { QuizHistoryItem, UserProfile } from '@/types'
import './index.scss'

const SLOGAN = '把知识做成关卡，一关一关闯下去。'

export default function Profile() {
  const [profile, setProfile] = useState<UserProfile | null>(null)
  const [history, setHistory] = useState<QuizHistoryItem[]>([])
  const [loading, setLoading] = useState(true)
  const [avatarUploading, setAvatarUploading] = useState(false)
  const [editingNickname, setEditingNickname] = useState(false)
  const [nicknameDraft, setNicknameDraft] = useState('')
  const [nicknameSaving, setNicknameSaving] = useState(false)

  const applyProfile = (p: UserProfile) => {
    setProfile(p)
    setCachedUser({ id: p.id, nickname: p.nickname, avatar_url: p.avatar_url, total_coins: p.total_coins })
  }

  const refresh = async () => {
    const logged = await ensureLogin()
    if (!logged) {
      setLoading(false)
      return
    }
    try {
      const [p, h] = await Promise.all([getProfile(), getQuizHistory(1, 20)])
      applyProfile(p)
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

  const uploadSelectedAvatar = async (tempPath: string) => {
    if (!tempPath || avatarUploading) return
    setAvatarUploading(true)
    try {
      const p = await uploadAvatar(tempPath)
      applyProfile(p)
      Taro.showToast({ title: '头像已更新', icon: 'success' })
    } catch (e) {
      const message = e instanceof ApiError ? e.message : '头像上传失败，请重试'
      Taro.showToast({ title: message, icon: 'none', duration: 2500 })
    } finally {
      setAvatarUploading(false)
    }
  }

  const onChooseAvatar = (event: { detail?: { avatarUrl?: string } }) => {
    const tempPath = event.detail?.avatarUrl
    if (tempPath) {
      void uploadSelectedAvatar(tempPath)
    }
  }

  const onAvatarTap = async () => {
    // chooseAvatar 仅微信小程序生效；H5 用相册/拍照入口走同一上传流程
    if (process.env.TARO_ENV === 'weapp' || avatarUploading) return
    try {
      const res = await Taro.chooseImage({
        count: 1,
        sizeType: ['compressed'],
        sourceType: ['album', 'camera']
      })
      const tempPath = res.tempFilePaths?.[0]
      if (tempPath) {
        await uploadSelectedAvatar(tempPath)
      }
    } catch (e) {
      // 用户取消选择
    }
  }

  const startEditNickname = () => {
    setNicknameDraft(profile?.nickname || '')
    setEditingNickname(true)
  }

  const cancelEditNickname = () => {
    setEditingNickname(false)
    setNicknameDraft('')
  }

  const saveNickname = async () => {
    if (nicknameSaving) return
    const nickname = nicknameDraft.trim()
    if (!nickname || nickname.length > 20) {
      Taro.showToast({ title: '昵称需为 1-20 字', icon: 'none' })
      return
    }
    if (nickname === profile?.nickname) {
      setEditingNickname(false)
      return
    }
    setNicknameSaving(true)
    try {
      const p = await updateProfile({ nickname })
      applyProfile(p)
      setEditingNickname(false)
      Taro.showToast({ title: '昵称已更新', icon: 'success' })
    } catch (e) {
      const message = e instanceof ApiError ? e.message : '修改失败，请重试'
      Taro.showToast({ title: message, icon: 'none', duration: 2500 })
    } finally {
      setNicknameSaving(false)
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
        <Button
          className='user-card__avatar'
          openType='chooseAvatar'
          hoverClass='none'
          disabled={avatarUploading}
          onChooseAvatar={onChooseAvatar}
          onClick={onAvatarTap}
        >
          <UserAvatar
            src={profile?.avatar_url || ''}
            name={nickname}
            className='user-card__avatar-inner'
          />
          {avatarUploading && (
            <View className='user-card__avatar-mask'>
              <Text>上传中</Text>
            </View>
          )}
        </Button>
        <View className='user-card__info'>
          {editingNickname ? (
            <View className='user-card__name-edit'>
              <Input
                className='user-card__name-input'
                type='nickname'
                value={nicknameDraft}
                maxlength={20}
                focus
                placeholder='输入昵称'
                onInput={e => setNicknameDraft(e.detail.value)}
                onConfirm={saveNickname}
              />
              <View
                className={`nickname-action ${nicknameSaving ? 'nickname-action--disabled' : ''}`}
                onClick={saveNickname}
              >
                <Text>保存</Text>
              </View>
              <View
                className='nickname-action nickname-action--ghost'
                onClick={cancelEditNickname}
              >
                <Text>取消</Text>
              </View>
            </View>
          ) : (
            <View className='user-card__name-row' onClick={startEditNickname}>
              <Text className='user-card__name'>{nickname}</Text>
              <View className='user-card__edit'>
                <Text>修改</Text>
              </View>
            </View>
          )}
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
