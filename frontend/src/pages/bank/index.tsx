import { useCallback, useEffect, useRef, useState } from 'react'
import { View, Text } from '@tarojs/components'
import Taro, { useDidHide, useDidShow } from '@tarojs/taro'
import TabBar from '@/components/TabBar'
import {
  createQuizJob,
  deleteKnowledgeDocument,
  getKnowledgeBase,
  getQuizJob,
  uploadKnowledgeDocument
} from '@/services/api'
import { ApiError } from '@/services/request'
import { ensureLogin } from '@/services/auth'
import { setCurrentQuiz } from '@/store'
import type { KnowledgeBaseOverview, KnowledgeDocument, KnowledgeDocumentStatus } from '@/types'
import './index.scss'

const POLL_INTERVAL_MS = 10000
const ACTIVE_JOB_KEY = 'ail_active_job'
const QUESTION_COUNT = 5
const ALLOWED_EXTENSIONS = ['pdf', 'docx', 'md', 'txt']
const JOB_POLL_FAST_MS = 3000
const JOB_POLL_SLOW_MS = 5000
const JOB_POLL_FAST_TRIES = 5
const JOB_POLL_MAX_WAIT_MS = 6 * 60 * 1000

interface ActiveJob {
  job_id: string
  user_input: string
  question_count: number
  created_at: number
  source?: 'home' | 'bank'
  doc_name?: string
}

function readActiveJob(): ActiveJob | null {
  const value = Taro.getStorageSync(ACTIVE_JOB_KEY)
  if (value && typeof value === 'object' && typeof (value as ActiveJob).job_id === 'string') {
    return value as ActiveJob
  }
  return null
}

function makeRequestId(): string {
  return `${Date.now()}_${Math.random().toString(36).slice(2, 10)}`
}

function formatSize(bytes: number): string {
  if (!bytes) return '0 KB'
  if (bytes >= 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`
  return `${Math.max(1, Math.round(bytes / 1024))} KB`
}

function statusLabel(status: KnowledgeDocumentStatus): string {
  if (status === 'ready') return '已就绪'
  if (status === 'failed') return '失败'
  return '处理中'
}

function isProcessing(doc: KnowledgeDocument): boolean {
  return doc.status === 'pending' || doc.status === 'processing'
}

export default function Bank() {
  const [overview, setOverview] = useState<KnowledgeBaseOverview | null>(null)
  const [loading, setLoading] = useState(true)
  const [uploading, setUploading] = useState(false)
  const [busyDocId, setBusyDocId] = useState('')
  const [generatingDocName, setGeneratingDocName] = useState('')
  const [error, setError] = useState('')

  const fileInputRef = useRef<HTMLInputElement | null>(null)
  const pollTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const jobPollTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const jobPollTokenRef = useRef(0)
  const jobPollingRef = useRef(false)
  const loadingRef = useRef(false)

  const load = useCallback(async (silent = false) => {
    if (loadingRef.current) return
    loadingRef.current = true
    if (!silent) setLoading(true)
    try {
      const logged = await ensureLogin()
      if (!logged) throw new ApiError(4010, '登录失败，请稍后重试')
      const data = await getKnowledgeBase()
      setOverview(data)
      setError('')
    } catch (e) {
      setError(e instanceof ApiError ? e.message : '知识库加载失败，请重试')
    } finally {
      loadingRef.current = false
      if (!silent) setLoading(false)
    }
  }, [])

  const stopJobPolling = useCallback(() => {
    jobPollTokenRef.current += 1
    jobPollingRef.current = false
    if (jobPollTimerRef.current) {
      clearTimeout(jobPollTimerRef.current)
      jobPollTimerRef.current = null
    }
  }, [])

  const finishJobFailure = useCallback(
    (message: string) => {
      stopJobPolling()
      Taro.removeStorageSync(ACTIVE_JOB_KEY)
      setGeneratingDocName('')
      setError(message || '生成失败，请重试')
      Taro.showToast({ title: message || '生成失败，请重试', icon: 'none', duration: 2500 })
    },
    [stopJobPolling]
  )

  const startJobPolling = useCallback(
    (job: ActiveJob) => {
      stopJobPolling()
      jobPollingRef.current = true
      setGeneratingDocName(job.doc_name || '当前文档')
      const token = jobPollTokenRef.current
      const startedAt = Date.now()

      const tick = async (attempt: number) => {
        if (token !== jobPollTokenRef.current) return

        try {
          const result = await getQuizJob(job.job_id)
          if (token !== jobPollTokenRef.current) return

          if (result.status === 'completed') {
            stopJobPolling()
            Taro.removeStorageSync(ACTIVE_JOB_KEY)
            setGeneratingDocName('')
            if (result.quiz) {
              setCurrentQuiz(result.quiz)
              await Taro.navigateTo({ url: '/pages/quiz/index' })
            } else {
              Taro.showToast({ title: '题库数据异常，请重试', icon: 'none', duration: 2500 })
            }
            return
          }

          if (result.status === 'failed') {
            finishJobFailure(result.error || '生成失败，请重试')
            return
          }
        } catch (e) {
          if (e instanceof ApiError && e.code !== -1) {
            finishJobFailure(e.message)
            return
          }
        }

        if (token !== jobPollTokenRef.current) return
        if (Date.now() - startedAt >= JOB_POLL_MAX_WAIT_MS) {
          finishJobFailure('生成超时，请重试')
          return
        }

        const delay = attempt < JOB_POLL_FAST_TRIES ? JOB_POLL_FAST_MS : JOB_POLL_SLOW_MS
        jobPollTimerRef.current = setTimeout(() => {
          void tick(attempt + 1)
        }, delay)
      }

      void tick(0)
    },
    [finishJobFailure, stopJobPolling]
  )

  useDidShow(() => {
    void load()
    const active = readActiveJob()
    if (active?.source === 'bank' && !jobPollingRef.current) {
      startJobPolling(active)
    }
  })

  useDidHide(() => {
    stopJobPolling()
    setGeneratingDocName('')
  })

  useEffect(() => {
    return () => {
      if (pollTimerRef.current) clearTimeout(pollTimerRef.current)
      if (jobPollTimerRef.current) clearTimeout(jobPollTimerRef.current)
    }
  }, [])

  const hasProcessing = Boolean(overview?.documents.some(isProcessing))
  useEffect(() => {
    if (!hasProcessing) return
    pollTimerRef.current = setTimeout(() => {
      void load(true)
    }, POLL_INTERVAL_MS)
    return () => {
      if (pollTimerRef.current) {
        clearTimeout(pollTimerRef.current)
        pollTimerRef.current = null
      }
    }
  }, [overview, hasProcessing, load])

  const uploadPath = useCallback(
    async (filePath: string, fileName: string) => {
      if (uploading) return
      setUploading(true)
      try {
        const logged = await ensureLogin()
        if (!logged) throw new ApiError(4010, '登录失败，请稍后重试')
        await uploadKnowledgeDocument(filePath, fileName)
        Taro.showToast({ title: '上传成功，正在解析…', icon: 'none' })
        await load(true)
      } catch (e) {
        const message = e instanceof ApiError ? e.message : '上传失败，请重试'
        setError(message)
        Taro.showToast({ title: message, icon: 'none', duration: 2500 })
      } finally {
        setUploading(false)
      }
    },
    [uploading, load]
  )

  const pickFile = () => {
    if (uploading) return
    if (process.env.TARO_ENV === 'h5') {
      fileInputRef.current?.click()
      return
    }
    Taro.chooseMessageFile({
      count: 1,
      type: 'file',
      extension: ALLOWED_EXTENSIONS
    })
      .then(res => {
        const file = res.tempFiles?.[0]
        if (file) void uploadPath(file.path, file.name)
      })
      .catch(() => {})
  }

  const onFileChange = (event: any) => {
    const target = event.target as HTMLInputElement
    const file = target.files?.[0]
    target.value = ''
    if (!file) return
    const objectUrl = URL.createObjectURL(file)
    void uploadPath(objectUrl, file.name).finally(() => URL.revokeObjectURL(objectUrl))
  }

  const onDelete = async (doc: KnowledgeDocument) => {
    if (busyDocId) return
    const modal = await Taro.showModal({
      title: '删除文档',
      content: `确定删除《${doc.file_name}》？删除后知识片段不可恢复。`,
      confirmText: '删除',
      confirmColor: '#d9534f'
    })
    if (!modal.confirm) return

    setBusyDocId(doc.doc_id)
    try {
      await deleteKnowledgeDocument(doc.doc_id)
      Taro.showToast({ title: '已删除', icon: 'none' })
      await load(true)
    } catch (e) {
      const message = e instanceof ApiError ? e.message : '删除失败，请重试'
      setError(message)
      Taro.showToast({ title: message, icon: 'none', duration: 2500 })
    } finally {
      setBusyDocId('')
    }
  }

  const onStart = async (doc: KnowledgeDocument) => {
    if (busyDocId || generatingDocName || doc.status !== 'ready') return
    setBusyDocId(doc.doc_id)
    setError('')
    try {
      const logged = await ensureLogin()
      if (!logged) throw new ApiError(4010, '登录失败，请稍后重试')

      const userInput = `请根据我的文档《${doc.file_name}》生成闯关题目，覆盖文档核心知识点。`
      const created = await createQuizJob({
        user_input: userInput,
        question_count: QUESTION_COUNT,
        difficulty: 'mixed',
        document_ids: [doc.doc_id],
        request_id: makeRequestId()
      })
      const job: ActiveJob = {
        job_id: created.job_id,
        user_input: userInput,
        question_count: QUESTION_COUNT,
        created_at: Date.now(),
        source: 'bank',
        doc_name: doc.file_name
      }
      Taro.setStorageSync(ACTIVE_JOB_KEY, job)
      startJobPolling(job)
    } catch (e) {
      const message = e instanceof ApiError ? e.message : '创建任务失败，请重试'
      setError(message)
      Taro.showToast({ title: message, icon: 'none', duration: 2500 })
    } finally {
      setBusyDocId('')
    }
  }

  const documents = overview?.documents || []
  const stats = overview?.stats

  return (
    <View className='page kb-page'>
      <View className='kb-head'>
        <Text className='kb-title'>我的知识库</Text>
        <Text className='kb-subtitle'>上传资料，AI 会从文档里出题</Text>
      </View>

      <View className={`upload-card ${uploading ? 'upload-card--busy' : ''}`} onClick={pickFile}>
        <View className='upload-card__plus'>
          <Text>+</Text>
        </View>
        <View className='upload-card__body'>
          <Text className='upload-card__title'>
            {uploading ? '正在上传…' : '上传文档建知识库'}
          </Text>
          <Text className='upload-card__desc'>支持 PDF / Word / Markdown / 文本，最大 10MB</Text>
        </View>
        <View className='icon icon-arrow-right upload-card__arrow' />
      </View>

      {process.env.TARO_ENV === 'h5' && (
        <input
          ref={fileInputRef}
          className='kb-file-input'
          type='file'
          accept='.pdf,.docx,.md,.txt'
          onChange={onFileChange}
        />
      )}

      {error && (
        <View className='kb-error'>
          <Text className='kb-error__text'>{error}</Text>
          <View className='kb-error__retry' onClick={() => void load()}>
            <Text>重试</Text>
          </View>
        </View>
      )}

      <View className='kb-list-head'>
        <Text className='kb-list-title'>我的文档</Text>
        {stats && stats.total_documents > 0 && (
          <Text className='kb-list-meta'>
            共 {stats.total_documents} 份 · {stats.total_chunks} 个知识片段
          </Text>
        )}
      </View>

      {loading ? (
        <View className='kb-empty'>
          <Text className='kb-empty__desc'>正在加载知识库…</Text>
        </View>
      ) : documents.length === 0 ? (
        <View className='kb-empty'>
          <View className='icon icon-book kb-empty__icon' />
          <Text className='kb-empty__title'>还没有文档</Text>
          <Text className='kb-empty__desc'>上传第一份资料，处理完成后就能一键闯关。</Text>
        </View>
      ) : (
        documents.map(doc => (
          <View className='doc-card' key={doc.doc_id}>
            <View className='doc-card__head'>
              <View className='doc-card__file'>
                <View className='doc-file-icon'>
                  <Text>{doc.file_ext.toUpperCase()}</Text>
                </View>
                <View className='doc-card__info'>
                  <Text className='doc-card__name'>{doc.file_name}</Text>
                  <Text className='doc-card__meta'>{formatSize(doc.file_size)}</Text>
                </View>
              </View>
              <View className={`status-chip status-chip--${doc.status}`}>
                <Text>{statusLabel(doc.status)}</Text>
              </View>
            </View>

            <View className='doc-card__status-line'>
              {doc.status === 'ready' ? (
                <Text className='doc-card__chunks'>共 {doc.chunk_count} 个知识片段</Text>
              ) : doc.status === 'failed' ? (
                <Text className='doc-card__error'>
                  {doc.error_message || '文档处理失败，请删除后重新上传'}
                </Text>
              ) : (
                <Text className='doc-card__processing'>AI 正在解析并建立知识片段，请稍候…</Text>
              )}
            </View>

            <View className='doc-card__actions'>
              <View
                className={`doc-btn doc-btn--start ${
                  doc.status !== 'ready' || busyDocId ? 'doc-btn--disabled' : ''
                }`}
                onClick={() => onStart(doc)}
              >
                <Text>{busyDocId === doc.doc_id ? '处理中…' : '开始闯关'}</Text>
              </View>
              <View
                className={`doc-btn doc-btn--delete ${busyDocId ? 'doc-btn--disabled' : ''}`}
                onClick={() => onDelete(doc)}
              >
                <Text>删除</Text>
              </View>
            </View>
          </View>
        ))
      )}

      <TabBar active='bank' />

      {generatingDocName && (
        <View className='kb-loading-mask'>
          <View className='kb-loading-card'>
            <View className='kb-loading-spinner' />
            <Text className='kb-loading-title'>AI 正在出题</Text>
            <Text className='kb-loading-doc'>《{generatingDocName}》</Text>
            <Text className='kb-loading-hint'>通常需要 30 秒到 1 分钟，请稍候…</Text>
          </View>
        </View>
      )}
    </View>
  )
}
