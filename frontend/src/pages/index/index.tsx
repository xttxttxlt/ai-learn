import { useCallback, useEffect, useRef, useState } from 'react'
import { ScrollView, Text, Textarea, View } from '@tarojs/components'
import Taro, { useDidHide, useDidShow, useReachBottom } from '@tarojs/taro'
import CoinPill from '@/components/CoinPill'
import ProgressRing from '@/components/ProgressRing'
import TabBar from '@/components/TabBar'
import UserAvatar from '@/components/UserAvatar'
import {
  createQuizJob,
  getKnowledgeBase,
  getProfile,
  getQuizHistory,
  getQuizJob
} from '@/services/api'
import { ApiError } from '@/services/request'
import { ensureLogin, getCachedUser, setCachedUser } from '@/services/auth'
import { formatHistoryDate, setCurrentQuiz } from '@/store'
import { accuracyColor } from '@/utils/accuracy'
import type { KnowledgeDocument, QuizHistoryItem, UserProfile } from '@/types'
import './index.scss'

const PLACEHOLDER = '可以是一段话、一个链接'

const ACTIVE_JOB_KEY = 'ail_active_job'
const HISTORY_PAGE_SIZE = 10
const POLL_FAST_MS = 3000
const POLL_SLOW_MS = 5000
const POLL_FAST_TRIES = 5
const POLL_MAX_WAIT_MS = 6 * 60 * 1000
const QUESTION_COUNT = 5

interface SelectedDoc {
  doc_id: string
  file_name: string
}

interface ActiveJob {
  job_id: string
  user_input: string
  question_count: number
  created_at: number
  generate_images?: boolean
  use_web_search?: boolean
  use_knowledge_base?: boolean
  document_id?: string
  document_name?: string
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

const DOC_PROMPTS = [
  (name: string) => `请根据文档《${name}》生成闯关题目，覆盖核心知识点。`,
  (name: string) => `围绕《${name}》的重点内容出题，帮我检验理解。`,
  (name: string) => `我刚开始读《${name}》，请出题帮我梳理关键概念。`,
  (name: string) => `请从《${name}》中提炼重点，生成一套闯关题。`,
  (name: string) => `用《${name}》的内容考考我，看看哪里还没掌握。`
]

let lastDocPromptIndex = -1

function docPrompt(fileName: string): string {
  let index = Math.floor(Math.random() * DOC_PROMPTS.length)
  if (index === lastDocPromptIndex) {
    index = (index + 1) % DOC_PROMPTS.length
  }
  lastDocPromptIndex = index
  return DOC_PROMPTS[index](fileName)
}

function truncateName(name: string, max = 10): string {
  return name.length > max ? `${name.slice(0, max)}…` : name
}

export default function Index() {
  const [text, setText] = useState('')
  const [generating, setGenerating] = useState(false)
  const [withWeb, setWithWeb] = useState(false)
  const [withImages, setWithImages] = useState(false)
  const [selectedDoc, setSelectedDoc] = useState<SelectedDoc | null>(null)
  const [autoFilledText, setAutoFilledText] = useState('')
  const [kbOpen, setKbOpen] = useState(false)
  const [kbLoading, setKbLoading] = useState(false)
  const [kbDocs, setKbDocs] = useState<KnowledgeDocument[]>([])
  const [kbError, setKbError] = useState('')
  const [profile, setProfile] = useState<UserProfile | null>(null)
  const [history, setHistory] = useState<QuizHistoryItem[]>([])
  const [historyPage, setHistoryPage] = useState(1)
  const [historyTotal, setHistoryTotal] = useState(0)
  const [historyLoading, setHistoryLoading] = useState(false)

  const pollTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const pollTokenRef = useRef(0)
  const pollingRef = useRef(false)

  const cached = getCachedUser()
  const nickname = profile?.nickname || cached?.nickname || '学习者'
  const coins = profile?.total_coins ?? cached?.total_coins ?? 0
  const avatarUrl = profile?.avatar_url || cached?.avatar_url || ''

  const caps = profile?.quiz_capabilities
  const webAvailable = Boolean(caps?.web_search)
  const kbAvailable = Boolean(caps?.knowledge_base)
  const quota = profile?.image_quota
  const quotaFull = Boolean(quota?.available && quota.remaining <= 0)
  const imageAvailable = Boolean(caps?.image_generation) && Boolean(quota?.available)
  const webDisabled = generating || !webAvailable
  const kbDisabled = generating || !kbAvailable
  const imageDisabled = generating || !imageAvailable || quotaFull || Boolean(selectedDoc)
  const imageText =
    quota && quota.available
      ? `今日配图（${quota.used}/${quota.limit}）`
      : '今日配图（暂不可用）'

  const historyHasMore = history.length < historyTotal

  const applyProfile = useCallback((p: UserProfile) => {
    setProfile(p)
    setCachedUser({ id: p.id, nickname: p.nickname, avatar_url: p.avatar_url, total_coins: p.total_coins })
  }, [])

  useEffect(() => {
    if (quotaFull || selectedDoc) setWithImages(false)
  }, [quotaFull, selectedDoc])

  useEffect(() => {
    if (!profile) return
    if (!webAvailable) setWithWeb(false)
    if (!kbAvailable) setSelectedDoc(null)
    if (!imageAvailable) setWithImages(false)
  }, [profile, webAvailable, kbAvailable, imageAvailable])

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
      const [p, h] = await Promise.all([getProfile(), getQuizHistory(1, HISTORY_PAGE_SIZE)])
      applyProfile(p)
      setHistory(h.items)
      setHistoryPage(1)
      setHistoryTotal(h.total)
    } catch (e) {
      // 拉取失败不打扰用户，展示缓存/空态
    }

    const active = readActiveJob()
    if (active && !pollingRef.current) {
      setText(prev => prev || active.user_input)
      setWithWeb(Boolean(active.use_web_search))
      setWithImages(Boolean(active.generate_images))
      if (active.use_knowledge_base && active.document_id) {
        setSelectedDoc({
          doc_id: active.document_id,
          file_name: active.document_name || '已选文档'
        })
      } else {
        setSelectedDoc(null)
      }
      startPolling(active)
    }
  })

  const loadMoreHistory = async () => {
    if (historyLoading || !historyHasMore) return
    setHistoryLoading(true)
    try {
      const next = historyPage + 1
      const h = await getQuizHistory(next, HISTORY_PAGE_SIZE)
      setHistory(prev => {
        const seen = new Set(prev.map(item => item.quiz_id))
        return [...prev, ...h.items.filter(item => !seen.has(item.quiz_id))]
      })
      setHistoryPage(h.page)
      setHistoryTotal(h.total)
    } catch (e) {
      // 触底加载失败保持现有列表，下次触底重试
    } finally {
      setHistoryLoading(false)
    }
  }

  useReachBottom(() => {
    void loadMoreHistory()
  })

  const toggleWeb = () => {
    if (webDisabled) return
    const next = !withWeb
    setWithWeb(next)
    if (next) setSelectedDoc(null)
  }

  const toggleImages = () => {
    if (imageDisabled) return
    setWithImages(prev => !prev)
  }

  const openKbPicker = async () => {
    if (kbDisabled) return
    setKbOpen(true)
    setKbLoading(true)
    setKbError('')
    try {
      const logged = await ensureLogin()
      if (!logged) throw new ApiError(4010, '登录失败，请稍后重试')
      const data = await getKnowledgeBase()
      setKbDocs(data.documents.filter(doc => doc.status === 'ready'))
    } catch (e) {
      setKbError(e instanceof ApiError ? e.message : '知识库加载失败，请重试')
    } finally {
      setKbLoading(false)
    }
  }

  const selectDoc = (doc: KnowledgeDocument) => {
    setSelectedDoc({ doc_id: doc.doc_id, file_name: doc.file_name })
    setWithWeb(false)
    setWithImages(false)
    setKbOpen(false)
    if (!text.trim() || text === autoFilledText) {
      const prompt = docPrompt(doc.file_name)
      setText(prompt)
      setAutoFilledText(prompt)
    }
  }

  const clearSelectedDoc = () => {
    if (text === autoFilledText) setText('')
    setAutoFilledText('')
    setSelectedDoc(null)
    setKbOpen(false)
  }

  const goToBank = () => {
    setKbOpen(false)
    void Taro.reLaunch({ url: '/pages/bank/index' })
  }

  const onGenerate = async () => {
    if (generating) return
    const input =
      selectedDoc && !text.trim() ? docPrompt(selectedDoc.file_name) : text.trim()
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
      const useKb = Boolean(selectedDoc)
      const useWeb = withWeb && !useKb
      const useImages = withImages && !useKb && !quotaFull && imageAvailable
      const documentId = selectedDoc?.doc_id
      const created = await createQuizJob({
        user_input: input,
        question_count: QUESTION_COUNT,
        use_web_search: useWeb,
        use_knowledge_base: useKb,
        document_id: useKb ? documentId : undefined,
        generate_images: useImages,
        request_id: makeRequestId()
      })
      const job: ActiveJob = {
        job_id: created.job_id,
        user_input: input,
        question_count: QUESTION_COUNT,
        created_at: Date.now(),
        generate_images: useImages,
        use_web_search: useWeb,
        use_knowledge_base: useKb,
        document_id: useKb ? documentId : undefined,
        document_name: useKb ? selectedDoc?.file_name : undefined
      }
      writeActiveJob(job)
      startPolling(job)
    } catch (e) {
      setGenerating(false)
      const msg = e instanceof ApiError ? e.message : '创建任务失败，请重试'
      Taro.showToast({ title: msg, icon: 'none', duration: 2500 })
    }
  }

  const generatingText = selectedDoc
    ? 'AI 检索文档出题中…'
    : withWeb
      ? 'AI 联网检索出题中…'
      : 'AI 出题中…'
  const generatingHint = selectedDoc
    ? '正在检索所选文档并出题，可能需要 1 分钟，可先退出稍后回来继续'
    : withWeb
      ? '联网检索与出题可能需要 1 分钟，可先退出稍后回来继续'
      : '通用出题通常需要 10~20 秒，可先退出稍后回来继续'

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

        <View className='mode-chips'>
          <View
            className={`mode-chip ${withWeb ? 'mode-chip--active' : ''} ${
              webDisabled ? 'mode-chip--disabled' : ''
            }`}
            onClick={toggleWeb}
          >
            <Text className='mode-chip__label'>联网检索</Text>
          </View>
          <View
            className={`mode-chip ${withImages ? 'mode-chip--active' : ''} ${
              imageDisabled ? 'mode-chip--disabled' : ''
            }`}
            onClick={toggleImages}
          >
            <Text className='mode-chip__label'>{imageText}</Text>
          </View>
          <View
            className={`mode-chip ${selectedDoc ? 'mode-chip--active mode-chip--doc' : ''} ${
              kbDisabled ? 'mode-chip--disabled' : ''
            }`}
            onClick={() => void openKbPicker()}
          >
            <Text className='mode-chip__label'>
              {selectedDoc ? truncateName(selectedDoc.file_name, 12) : '知识库'}
            </Text>
          </View>
        </View>

        <View className='home-actions'>
          <View className={`home-btn ${generating ? 'home-btn--disabled' : ''}`} onClick={onGenerate}>
            <View className='icon icon-arrow-right home-btn__icon' />
            <Text>{generating ? generatingText : '开始生成题目'}</Text>
          </View>
        </View>
        {generating && <Text className='home-hint'>{generatingHint}</Text>}
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
                color={accuracyColor(item.accuracy)}
              />
            ) : (
              <Text className='item__status'>
                {item.answered_count ? `已答 ${item.answered_count}/${item.question_count ?? ''}` : '未完成'}
              </Text>
            )}
          </View>
        ))
      )}

      {history.length > 0 && (historyLoading || (!historyHasMore && history.length > HISTORY_PAGE_SIZE)) && (
        <Text className='list-foot'>{historyLoading ? '加载中…' : '没有更多了'}</Text>
      )}

      {kbOpen && (
        <View className='kb-sheet-mask' onClick={() => setKbOpen(false)}>
          <View className='kb-sheet' onClick={e => e.stopPropagation()}>
            <View className='kb-sheet__head'>
              <View className='kb-sheet__title-wrap'>
                <Text className='kb-sheet__title'>选择知识库文档</Text>
                <Text className='kb-sheet__subtitle'>仅显示已就绪文档，单选一份</Text>
              </View>
              <Text className='kb-sheet__close' onClick={() => setKbOpen(false)}>
                关闭
              </Text>
            </View>

            {kbLoading ? (
              <Text className='kb-sheet__state'>正在加载知识库…</Text>
            ) : kbError ? (
              <View className='kb-sheet__state'>
                <Text className='kb-sheet__error'>{kbError}</Text>
                <Text className='kb-sheet__retry' onClick={() => void openKbPicker()}>
                  重试
                </Text>
              </View>
            ) : kbDocs.length === 0 ? (
              <View className='kb-sheet__empty'>
                <Text className='kb-sheet__empty-title'>还没有可用文档</Text>
                <Text className='kb-sheet__empty-desc'>
                  先到题库上传资料，处理完成后就能在这里选择。
                </Text>
                <View className='kb-sheet__upload' onClick={goToBank}>
                  <Text>去题库上传</Text>
                </View>
              </View>
            ) : (
              <ScrollView scrollY className='kb-sheet__list'>
                {kbDocs.map(doc => (
                  <View
                    key={doc.doc_id}
                    className={`kb-doc ${
                      selectedDoc?.doc_id === doc.doc_id ? 'kb-doc--selected' : ''
                    }`}
                    onClick={() => selectDoc(doc)}
                  >
                    <View className='kb-doc__body'>
                      <Text className='kb-doc__name'>{doc.file_name}</Text>
                      <Text className='kb-doc__meta'>共 {doc.chunk_count} 个知识片段</Text>
                    </View>
                    <View
                      className={`kb-doc__radio ${
                        selectedDoc?.doc_id === doc.doc_id ? 'kb-doc__radio--checked' : ''
                      }`}
                    />
                  </View>
                ))}
              </ScrollView>
            )}

            {selectedDoc && (
              <View className='kb-sheet__clear' onClick={clearSelectedDoc}>
                <Text>清除选择</Text>
              </View>
            )}
          </View>
        </View>
      )}

      <TabBar active='home' />
    </View>
  )
}
