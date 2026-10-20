import { useState } from 'react'
import { View, Text } from '@tarojs/components'
import Taro, { useLoad } from '@tarojs/taro'
import CoinPill from '@/components/CoinPill'
import { getCachedUser } from '@/services/auth'
import { getQuizDetail, saveQuizProgress } from '@/services/api'
import { COIN_PER_CORRECT, getCurrentQuiz, setCurrentQuiz, setAnswerRecords } from '@/store'
import { isKnowledgeBaseSource, knowledgeBaseMeta } from '@/utils/source'
import type { AnswerRecord, Question, Quiz } from '@/types'
import './index.scss'

function isCorrect(selected: string[], answer: string[]): boolean {
  const s = [...new Set(selected)].sort()
  const a = [...new Set(answer)].sort()
  return s.length === a.length && s.every((v, i) => v === a[i])
}

const TYPE_LABEL: Record<Question['type'], string> = {
  single: '单选',
  multiple: '多选',
  judge: '判断'
}

/** 题干中不再展示（单选）（多选）（判断）字样，题型由气泡标识 */
function stripTypeTag(stem: string): string {
  return stem
    .replace(/[（(]\s*(单选|多选|判断)\s*[)）]/g, '')
    .trim()
}

export default function QuizPage() {
  const [quiz, setQuiz] = useState<Quiz | null>(null)
  const [loading, setLoading] = useState(true)
  const [idx, setIdx] = useState(0)
  const [records, setRecords] = useState<Record<string, AnswerRecord>>({})
  const [pending, setPending] = useState<string[]>([])
  const [startTs, setStartTs] = useState(Date.now())
  // 金币基数取服务端缓存的 total_coins，本局答对即时累加（落库以报告接口为准）
  const [coinTotal, setCoinTotal] = useState<number>(getCachedUser()?.total_coins ?? 0)
  const [explainOpen, setExplainOpen] = useState(true)
  const [sourcesOpen, setSourcesOpen] = useState(false)

  // 支持断点续答：URL 带 quiz_id 时从后端拉题库，并按本地进度恢复题号与已答记录
  useLoad(options => {
    const qid = options?.quiz_id
    if (!qid) {
      setQuiz(getCurrentQuiz())
      setLoading(false)
      return
    }
    ;(async () => {
      try {
        const detail = await getQuizDetail(qid)
        const resumed: Quiz = {
          quiz_id: detail.quiz_id,
          title: detail.title,
          summary: detail.summary,
          sources: detail.sources,
          grounded: detail.grounded,
          questions: detail.questions
        }
        setCurrentQuiz(resumed)
        setQuiz(resumed)
        const progRecords = detail.progress || []
        if (progRecords.length > 0) {
          const map: Record<string, AnswerRecord> = {}
          progRecords.forEach(r => {
            map[r.question_id] = r
          })
          setRecords(map)
          setIdx(Math.max(0, Math.min(detail.current_index ?? 0, detail.questions.length - 1)))
        }
      } catch (e) {
        setQuiz(null)
      } finally {
        setLoading(false)
      }
    })()
  })

  if (loading) {
    return (
      <View className='page quiz-empty'>
        <Text className='quiz-empty__text'>加载中…</Text>
      </View>
    )
  }

  if (!quiz || quiz.questions.length === 0) {
    return (
      <View className='page quiz-empty'>
        <Text className='quiz-empty__text'>未找到题目，请返回首页重新开始。</Text>
        <View className='quiz-empty__btn' onClick={() => Taro.reLaunch({ url: '/pages/index/index' })}>
          <Text>返回首页</Text>
        </View>
      </View>
    )
  }

  const persistProgress = (nextIdx: number, nextRecords: Record<string, AnswerRecord>) => {
    // 进度上报后端（fire-and-forget，失败不阻塞答题）
    saveQuizProgress({
      quiz_id: quiz.quiz_id,
      index: nextIdx,
      records: Object.values(nextRecords)
    }).catch(() => {})
  }

  const total = quiz.questions.length
  const q = quiz.questions[idx]
  const rec = records[q.id]
  const submitted = !!rec
  const selected = submitted ? rec.selected_answers : pending
  const isLast = idx === total - 1
  const correctCount = Object.values(records).filter(r => r.is_correct).length

  const goTo = (next: number) => {
    setIdx(next)
    setPending([])
    setStartTs(Date.now())
    setExplainOpen(true)
    persistProgress(next, records)
  }

  const submit = (keys: string[]) => {
    if (keys.length === 0) {
      Taro.showToast({ title: '请先选择答案', icon: 'none' })
      return
    }
    const correct = isCorrect(keys, q.answer)
    const record: AnswerRecord = {
      question_id: q.id,
      selected_answers: keys,
      is_correct: correct,
      duration_ms: Date.now() - startTs
    }
    const nextRecords = { ...records, [q.id]: record }
    setRecords(nextRecords)
    persistProgress(idx, nextRecords)
    if (correct) {
      setCoinTotal(prev => prev + COIN_PER_CORRECT)
    }
  }

  const onOption = (key: string) => {
    if (submitted) return
    if (q.type === 'multiple') {
      setPending(prev => (prev.includes(key) ? prev.filter(k => k !== key) : [...prev, key]))
    } else {
      submit([key])
    }
  }

  const onPrev = () => {
    if (idx > 0) goTo(idx - 1)
  }

  const onFinish = () => {
    const list = quiz.questions.map(item => records[item.id]).filter(Boolean) as AnswerRecord[]
    setAnswerRecords(list)
    setCurrentQuiz(quiz)
    Taro.redirectTo({ url: '/pages/report/index' })
  }

  const onNext = () => {
    // 多选题无单独确认按钮：未作答时"继续"即确认作答，作答后再次点击才进入下一题
    if (!submitted) {
      if (q.type === 'multiple') submit(pending)
      return
    }
    if (isLast) onFinish()
    else goTo(idx + 1)
  }

  const optionClass = (key: string) => {
    let cls = 'option'
    if (submitted) {
      if (q.answer.includes(key)) cls += ' option--right'
      else if (selected.includes(key)) cls += ' option--wrong'
      else cls += ' option--muted'
    } else if (selected.includes(key)) {
      cls += ' option--selected'
    }
    return cls
  }

  const progressPct = Math.round(((idx + 1) / total) * 100)

  const copyUrl = (url: string) => {
    Taro.setClipboardData({ data: url })
  }

  return (
    <View className='page'>
      <View className='quiz-head'>
        <Text className='quiz-head__count'>
          第 {idx + 1} / {total} 题
        </Text>
        <CoinPill value={coinTotal} />
      </View>

      <View className='quiz-progress'>
        <View className='track'>
          <View className='track__bar' style={{ width: `${progressPct}%` }} />
        </View>
        <View className='meta'>
          <Text>答对 {correctCount} 题</Text>
          <Text>剩余 {total - idx - 1} 题</Text>
        </View>
      </View>

      <Text className='quiz-title'>
        {stripTypeTag(q.stem)}
        <Text className={`qtype qtype--${q.type}`}>{TYPE_LABEL[q.type]}</Text>
      </Text>

      <View className='options'>
        {q.options.map(opt => (
          <View key={opt.key} className={optionClass(opt.key)} onClick={() => onOption(opt.key)}>
            {submitted && q.answer.includes(opt.key) && (
              <View className='icon icon-check-green option__mark' />
            )}
            {submitted && !q.answer.includes(opt.key) && selected.includes(opt.key) && (
              <View className='icon icon-cross-red option__mark' />
            )}
            <Text className='option__text'>{opt.text}</Text>
          </View>
        ))}
      </View>

      {submitted && (
        <View className={`result-tip ${rec.is_correct ? 'result-tip--ok' : 'result-tip--bad'}`}>
          <View className='result-tip__left'>
            <View
              className={`icon result-tip__icon ${rec.is_correct ? 'icon-check-small' : 'icon-cross-red'}`}
            />
            <Text>{rec.is_correct ? '答对啦' : '答错了'}</Text>
          </View>
          <View className='result-tip__right'>
            <Text>+{rec.is_correct ? COIN_PER_CORRECT : 0}</Text>
            <View className='icon icon-coin result-tip__coin' />
          </View>
        </View>
      )}

      {submitted && (
        <View className='explain-box'>
          <View className='explain-head' onClick={() => setExplainOpen(o => !o)}>
            <Text className='explain-head__label'>解析</Text>
            <Text className='explain-head__toggle'>{explainOpen ? '收起' : '展开'}</Text>
          </View>
          {explainOpen && <Text className='explain-body'>{q.explanation}</Text>}
        </View>
      )}

      {quiz.sources && quiz.sources.length > 0 && (
        <View className='sources-box'>
          <View className='sources-head' onClick={() => setSourcesOpen(o => !o)}>
            <Text className='sources-head__label'>参考来源（{quiz.sources.length}）</Text>
            <Text className='sources-head__toggle'>{sourcesOpen ? '收起' : '展开'}</Text>
          </View>
          {sourcesOpen &&
            quiz.sources.map((s, i) => {
              const kb = isKnowledgeBaseSource(s)
              const meta = kb ? knowledgeBaseMeta(s) : ''
              return (
                <View
                  className={`source-item ${kb ? 'source-item--kb' : ''}`}
                  key={`${s.kind || 'web'}-${s.doc_id || ''}-${s.chunk_index ?? i}`}
                  onClick={() => {
                    if (!kb && s.url) copyUrl(s.url)
                  }}
                >
                  <View className='source-item__head'>
                    {kb && <Text className='source-item__badge'>知识库</Text>}
                    <Text className='source-item__title'>{s.title}</Text>
                  </View>
                  {kb ? (
                    <>
                      {meta && <Text className='source-item__meta'>{meta}</Text>}
                      {s.snippet && <Text className='source-item__snippet'>{s.snippet}</Text>}
                    </>
                  ) : (
                    <Text className='source-item__url'>{s.url}</Text>
                  )}
                </View>
              )
            })}
        </View>
      )}

      <View className='next'>
        <View className={`prev-btn ${idx === 0 ? 'btn--disabled' : ''}`} onClick={onPrev}>
          <Text>上一题</Text>
        </View>
        <View
          className={`next-btn ${!submitted && q.type !== 'multiple' ? 'btn--disabled' : ''}`}
          onClick={onNext}
        >
          <Text>{isLast ? '查看报告' : '继续'} →</Text>
        </View>
      </View>
    </View>
  )
}
