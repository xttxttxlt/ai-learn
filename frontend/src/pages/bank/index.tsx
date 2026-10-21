import { useCallback, useEffect, useRef, useState } from 'react'
import { View, Text } from '@tarojs/components'
import Taro, { useDidShow, useReachBottom } from '@tarojs/taro'
import TabBar from '@/components/TabBar'
import {
  deleteKnowledgeDocument,
  getKnowledgeDocuments,
  uploadKnowledgeDocument
} from '@/services/api'
import { ApiError } from '@/services/request'
import { ensureLogin } from '@/services/auth'
import type { KnowledgeDocument, KnowledgeDocumentStatus } from '@/types'
import './index.scss'

const POLL_INTERVAL_MS = 10000
const PAGE_SIZE = 10
const ALLOWED_EXTENSIONS = ['pdf', 'docx', 'md', 'txt']

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
  const [documents, setDocuments] = useState<KnowledgeDocument[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(true)
  const [loadingMore, setLoadingMore] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [busyDocId, setBusyDocId] = useState('')
  const [error, setError] = useState('')

  const fileInputRef = useRef<HTMLInputElement | null>(null)
  const pollTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const loadingRef = useRef(false)

  const load = useCallback(async (silent = false, pages = 1) => {
    if (loadingRef.current) return
    loadingRef.current = true
    if (!silent) setLoading(true)
    try {
      const logged = await ensureLogin()
      if (!logged) throw new ApiError(4010, '登录失败，请稍后重试')
      let items: KnowledgeDocument[] = []
      let count = 0
      for (let p = 1; p <= pages; p += 1) {
        const data = await getKnowledgeDocuments(p, PAGE_SIZE)
        items = [...items, ...data.items]
        count = data.total
        if (items.length >= count) break
      }
      setDocuments(items)
      setTotal(count)
      setPage(Math.max(1, Math.ceil(items.length / PAGE_SIZE)))
      setError('')
    } catch (e) {
      setError(e instanceof ApiError ? e.message : '知识库加载失败，请重试')
    } finally {
      loadingRef.current = false
      if (!silent) setLoading(false)
    }
  }, [])

  const loadMore = async () => {
    if (loadingRef.current || documents.length >= total) return
    loadingRef.current = true
    setLoadingMore(true)
    try {
      const data = await getKnowledgeDocuments(page + 1, PAGE_SIZE)
      setDocuments(prev => {
        const seen = new Set(prev.map(doc => doc.doc_id))
        return [...prev, ...data.items.filter(doc => !seen.has(doc.doc_id))]
      })
      setTotal(data.total)
      setPage(data.page)
    } catch (e) {
      // 触底加载失败保持现有列表，下次触底重试
    } finally {
      loadingRef.current = false
      setLoadingMore(false)
    }
  }

  useDidShow(() => {
    void load()
  })

  useReachBottom(() => {
    void loadMore()
  })

  useEffect(() => {
    return () => {
      if (pollTimerRef.current) clearTimeout(pollTimerRef.current)
    }
  }, [])

  const hasProcessing = documents.some(isProcessing)
  useEffect(() => {
    if (!hasProcessing) return
    pollTimerRef.current = setTimeout(() => {
      void load(true, page)
    }, POLL_INTERVAL_MS)
    return () => {
      if (pollTimerRef.current) {
        clearTimeout(pollTimerRef.current)
        pollTimerRef.current = null
      }
    }
  }, [documents, hasProcessing, load, page])

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

  return (
    <View className='page kb-page'>
      <View className='kb-head'>
        <Text className='kb-title'>我的知识库</Text>
        <Text className='kb-subtitle'>上传资料，在首页选择文档出题</Text>
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
        {total > 0 && <Text className='kb-list-meta'>共 {total} 份</Text>}
      </View>

      {loading ? (
        <View className='kb-empty'>
          <Text className='kb-empty__desc'>正在加载知识库…</Text>
        </View>
      ) : documents.length === 0 ? (
        <View className='kb-empty'>
          <View className='icon icon-book kb-empty__icon' />
          <Text className='kb-empty__title'>还没有文档</Text>
          <Text className='kb-empty__desc'>上传第一份资料，处理完成后就能在首页选择它出题。</Text>
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

            <View className='doc-card__foot'>
              <View className='doc-card__foot-text'>
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
              <View
                className={`doc-btn doc-btn--delete ${busyDocId ? 'doc-btn--disabled' : ''}`}
                onClick={() => onDelete(doc)}
              >
                <Text>{busyDocId === doc.doc_id ? '处理中…' : '删除'}</Text>
              </View>
            </View>
          </View>
        ))
      )}

      {documents.length > 0 &&
        (loadingMore || (documents.length >= total && documents.length > PAGE_SIZE)) && (
          <Text className='kb-list-foot'>
            {loadingMore ? '加载中…' : '没有更多了'}
          </Text>
        )}

      <TabBar active='bank' />
    </View>
  )
}
