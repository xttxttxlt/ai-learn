import { useState } from 'react'
import { View, Text, Textarea } from '@tarojs/components'
import Taro, { useDidShow } from '@tarojs/taro'
import CoinPill from '@/components/CoinPill'
import ProgressRing from '@/components/ProgressRing'
import TabBar from '@/components/TabBar'
import { generateQuiz, getProfile, getQuizHistory } from '@/services/api'
import { ApiError } from '@/services/request'
import { ensureLogin, getCachedUser, setCachedUser } from '@/services/auth'
import { formatHistoryDate, setCurrentQuiz } from '@/store'
import type { QuizHistoryItem, UserProfile } from '@/types'
import './index.scss'

const PLACEHOLDER =
  '例如：RAG 和传统搜索有什么区别？\n我想顺便搞懂向量数据库是怎么配合工作的。\n最好通过闯关题帮我记住重点。'

export default function Index() {
  const [text, setText] = useState('')
  const [loading, setLoading] = useState(false)
  const [profile, setProfile] = useState<UserProfile | null>(null)
  const [history, setHistory] = useState<QuizHistoryItem[]>([])

  const cached = getCachedUser()
  const nickname = profile?.nickname || cached?.nickname || '学习者'
  const coins = profile?.total_coins ?? cached?.total_coins ?? 0

  useDidShow(async () => {
    const logged = await ensureLogin()
    if (!logged) return
    try {
      const [p, h] = await Promise.all([getProfile(), getQuizHistory(1, 10)])
      setProfile(p)
      setCachedUser({ id: p.id, nickname: p.nickname, avatar_url: p.avatar_url, total_coins: p.total_coins })
      setHistory(h.items)
    } catch (e) {
      // 拉取失败不打扰用户，展示缓存/空态
    }
  })

  const onGenerate = async () => {
    if (loading) return
    const input = text.trim()
    if (!input) {
      Taro.showToast({ title: '先输入想学的内容', icon: 'none' })
      return
    }
    setLoading(true)
    Taro.showLoading({ title: 'AI 出题中…', mask: true })
    try {
      const quiz = await generateQuiz({ user_input: input, question_count: 5 })
      setCurrentQuiz(quiz)
      Taro.hideLoading()
      await Taro.navigateTo({ url: '/pages/quiz/index' })
    } catch (e) {
      Taro.hideLoading()
      const msg = e instanceof ApiError ? e.message : '生成失败，请重试'
      Taro.showToast({ title: msg, icon: 'none', duration: 2500 })
    } finally {
      setLoading(false)
    }
  }

  const openHistory = (quizId: string) => {
    Taro.navigateTo({ url: `/pages/report/index?quiz_id=${quizId}` })
  }

  return (
    <View className='page'>
      <View className='toolbar'>
        <View className='hello-user'>
          <View className='hello-avatar'>
            <Text>{nickname.slice(0, 1)}</Text>
          </View>
          <Text className='hello-name'>你好，{nickname}</Text>
        </View>
        <CoinPill value={coins} />
      </View>

      <Text className='title'>今天想闯哪一关？</Text>

      <View className='quick-input'>
        <View className='quick-input-head'>
          <View className='quick-label'>
            <Text>输入你想学的内容</Text>
          </View>
          <View className='mini-mascot'>
            <View className='icon icon-mascot mini-mascot__icon' />
          </View>
        </View>
        <Textarea
          className='quick-textarea'
          value={text}
          placeholder={PLACEHOLDER}
          placeholderClass='quick-textarea__ph'
          maxlength={2000}
          onInput={e => setText(e.detail.value)}
        />
        <View className='home-actions'>
          <View className={`home-btn ${loading ? 'home-btn--disabled' : ''}`} onClick={onGenerate}>
            <View className='icon icon-arrow-right home-btn__icon' />
            <Text>{loading ? 'AI 正在出题…' : '开始生成题目'}</Text>
          </View>
        </View>
      </View>

      <Text className='list-title'>历史记录</Text>

      {history.length === 0 ? (
        <View className='empty'>
          <Text>还没有闯关记录，先去闯一关吧～</Text>
        </View>
      ) : (
        history.map(item => (
          <View className='item' key={item.quiz_id} onClick={() => openHistory(item.quiz_id)}>
            <View className='item__avatar'>
              <View className='icon icon-book item__avatar-icon' />
            </View>
            <View className='item__body'>
              <Text className='item__title'>{item.title}</Text>
              <Text className='item__date'>{formatHistoryDate(item.created_at)}</Text>
            </View>
            {item.accuracy !== null && (
              <ProgressRing
                percent={item.accuracy}
                size='sm'
                color={item.accuracy >= 50 ? '#ff7a2f' : '#47a4ff'}
              />
            )}
          </View>
        ))
      )}

      <TabBar active='home' />
    </View>
  )
}
