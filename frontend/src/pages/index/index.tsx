import { useCallback, useEffect, useRef, useState } from 'react'
import { View, Text, Textarea, Switch } from '@tarojs/components'
import Taro, { useDidHide, useDidShow } from '@tarojs/taro'
import CoinPill from '@/components/CoinPill'
import ProgressRing from '@/components/ProgressRing'
import TabBar from '@/components/TabBar'
import UserAvatar from '@/components/UserAvatar'
import { createQuizJob, getProfile, getQuizHistory, getQuizJob } from '@/services/api'
import { ApiError } from '@/services/request'
import { ensureLogin, getCachedUser, setCachedUser } from '@/services/auth'
import { formatHistoryDate, setCurrentQuiz } from '@/store'
import type { QuizHistoryItem, UserProfile } from '@/types'
import './index.scss'

const PLACEHOLDER =
  '例如：RAG 和传统搜索有什么区别？\n我想顺便搞定向量数据库是怎么配合工作的。\n最好通过闯关题帮我记住重点。'

const ACTIVE_JOB_KEY = 'ail_active_job'
const POLL_FAST_MS = 3000
const POLL_SLOW_MS = 5000
const POLL_FAST_TRIES = 5
const POLL_MAX_WAIT_MS = 6 * 60 * 1000
const QUESTION_COUNT = 5

interface ActiveJob {
  job_id: string
  user_input: string
  question_count: number
  created_at: number
  generate_images?: boolean
}

function readActiveJob(): ActiveJob | null {
  const value = Taro.getStorageSync(ACTIVE_JOB_KEY)
  if (value && typeof value === 'object' && typeof (value as ActiveJob).job_id === 'string') {
    return value as ActiveJob
  }
  return null
}

function writeActiveJob(job: ActiveJob) {
  Taro.setStorageSync(ACTIVE_JOB_KEY, job)
}

function clearActiveJob() {
  Taro.removeStorageSync(ACTIVE_JOB_KEY)
}

function makeRequestId(): string {
  return `${Date.now()}_${Math.random().toString(36).slice(2, 10)}`
}

export default function Index() {
  const [text, setText] = useState('')
  const [generating, setGenerating] = useState(false)
  const [withImages, setWithImages] = useState(false)
  const [profile, setProfile] = useState<UserProfile | null>(null)
  const [history, setHistory] = useState<QuizHistoryItem[]>([])

  const pollTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const pollTokenRef = useRef(0)
  const pollingRef = useRef(false)

  const cached = getCachedUser()
  const nickname = profile?.nickname || cached?.nickname || '学习者'
  const coins = profile?.total_coins ?? cached?.total_coins ?? 0
  const avatarUrl = profile?.avatar_url || cached?.avatar_url || ''

  const quota = profile?.image_quota
  const quotaFull = Boolean(quota?.available && quota.remaining <= 0)
  const quotaText = !quota
    ? '今日配图 --/100'
    : !quota.available
      ? '今日配图 暂不可用'
      : quotaFull
        ? `今日配图 ${quota.used}/${quota.limit}，额度已用完`
        : `今日配图 ${quota.used}/${quota.limit}`

  const applyProfile = useCallback((p: UserProfile) => {
    setProfile(p)
    setCachedUser({ id: p.id, nickname: p.nickname, avatar_url: p.avatar_url, total_coins: p.total_coins })
  }, [])

  useEffect(() => {
    if (quotaFull) setWithImages(false)
  }, [quotaFull])

  const stopPolling = useCallback(() => {
    pollTokenRef.current += 1
    pollingRef.current = false
    if (pollTimerRef.current) {
      clearTimeout(pollTimerRef.current)
      pollTimerRef.current = null
    }
  }, [])

  const finishFailure = useCallback(
    (job: ActiveJob | null, message: string) => {
      stopPolling()
      clearActiveJob()
      setGenerating(false)
      if (job) setText(prev => prev || job.user_input)
      Taro.showToast({ title: message || '生成失败，请重试', icon: 'none', duration: 2500 })
    },
    [stopPolling]
  )

  const startPolling = useCallback(
    (job: ActiveJob) => {
      stopPolling()
      pollingRef.current = true
      setGenerating(true)
      const token = pollTokenRef.current
      const startedAt = Date.now()

      const tick = async (attempt: number) => {
        if (token !== pollTokenRef.current) return

        try {
          const result = await getQuizJob(job.job_id)
          if (token !== pollTokenRef.current) return

          if (result.status === 'completed') {
            stopPolling()
            clearActiveJob()
            setGenerating(false)
            void getProfile().then(applyProfile).catch(() => {})
            if (result.quiz) {
              setCurrentQuiz(result.quiz)
              await Taro.navigateTo({ url: '/pages/quiz/index' })
            } else {
              Taro.showToast({ title: '题库数据异常，请重试', icon: 'none', duration: 2500 })
            }
            return
          }

          if (result.status === 'failed') {
            finishFailure(job, result.error || '生成失败，请重试')
            return
          }
        } catch (e) {
          // 网络异常继续重试；业务错误（任务不存在、鉴权失败等）直接结束
          if (e instanceof ApiError && e.code !== -1) {
            finishFailure(job, e.message)
            return
          }
        }

        if (token !== pollTokenRef.current) return
        if (Date.now() - startedAt >= POLL_MAX_WAIT_MS) {
          finishFailure(job, '生成超时，请重试')
          return
        }

        const delay = attempt < POLL_FAST_TRIES ? POLL_FAST_MS : POLL_SLOW_MS
        pollTimerRef.current = setTimeout(() => {
          void tick(attempt + 1)
        }, delay)
      }

      void tick(0)
    },
    [applyProfile, finishFailure, stopPolling]
  )

  useEffect(() => {
    return () => stopPolling()
  }, [stopPolling])

  useDidHide(() => {
    stopPolling()
    setGenerating(false)
  })

  useDidShow(async () => {
    const logged = await ensureLogin()
    if (!logged) return
    try {
      const [p, h] = await Promise.all([getProfile(), getQuizHistory(1, 10)])
      applyProfile(p)
      setHistory(h.items)
    } catch (e) {
      // 拉取失败不打扰用户，展示缓存/空态
    }

    const active = readActiveJob()
    if (active && !pollingRef.current) {
      setText(prev => prev || active.user_input)
      setWithImages(Boolean(active.generate_images))
      startPolling(active)
    }
  })

  const onGenerate = async () => {
    if (generating) return
    const input = text.trim()
    if (!input) {
      Taro.showToast({ title: '先输入想学的内容', icon: 'none' })
      return
    }

    const logged = await ensureLogin()
    if (!logged) {
      Taro.showToast({ title: '登录失败，请稍后重试', icon: 'none' })
      return
    }

    setGenerating(true)
    try {
      const useImages = withImages && !quotaFull
      const created = await createQuizJob({
        user_input: input,
        question_count: QUESTION_COUNT,
        generate_images: useImages,
        request_id: makeRequestId()
      })
      const job: ActiveJob = {
        job_id: created.job_id,
        user_input: input,
        question_count: QUESTION_COUNT,
        created_at: Date.now(),
        generate_images: useImages
      }
      writeActiveJob(job)
      startPolling(job)
    } catch (e) {
      setGenerating(false)
      const msg = e instanceof ApiError ? e.message : '创建任务失败，请重试'
      Taro.showToast({ title: msg, icon: 'none', duration: 2500 })
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

  return (
    <View className='page'>
      <View className='toolbar'>
        <View className='hello-user'>
          <UserAvatar src={avatarUrl} name={nickname} className='hello-avatar' />
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
        <View className='image-toggle'>
          <View className='image-toggle__text'>
            <Text className='image-toggle__label'>生成配图</Text>
            <Text className='image-toggle__desc'>每题配一张相关图片，{quotaText}</Text>
          </View>
          <Switch
            className='image-toggle__switch'
            checked={withImages && !quotaFull}
            color='#ff7a2f'
            disabled={generating || quotaFull}
            onChange={e => setWithImages(e.detail.value)}
          />
        </View>
        <View className='home-actions'>
          <View className={`home-btn ${generating ? 'home-btn--disabled' : ''}`} onClick={onGenerate}>
            <View className='icon icon-arrow-right home-btn__icon' />
            <Text>{generating ? 'AI 检索出题中…' : '开始生成题目'}</Text>
          </View>
        </View>
        {generating && (
          <Text className='home-hint'>联网检索与出题可能需要 1 分钟，可先退出稍后回来继续</Text>
        )}
      </View>

      <Text className='list-title'>历史记录</Text>

      {history.length === 0 ? (
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

      <TabBar active='home' />
    </View>
  )
}
