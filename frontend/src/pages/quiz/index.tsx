import { useState } from 'react'
import { View, Text } from '@tarojs/components'
import Taro from '@tarojs/taro'
import CoinPill from '@/components/CoinPill'
import { getCachedUser } from '@/services/auth'
import { COIN_PER_CORRECT, getCurrentQuiz, setAnswerRecords } from '@/store'
import type { AnswerRecord, Quiz } from '@/types'
import './index.scss'

function isCorrect(selected: string[], answer: string[]): boolean {
  const s = [...new Set(selected)].sort()
  const a = [...new Set(answer)].sort()
  return s.length === a.length && s.every((v, i) => v === a[i])
}

export default function QuizPage() {
  const [quiz] = useState<Quiz | null>(getCurrentQuiz())
  const [idx, setIdx] = useState(0)
  const [records, setRecords] = useState<Record<string, AnswerRecord>>({})
  const [pending, setPending] = useState<string[]>([])
  const [startTs, setStartTs] = useState(Date.now())
  // 金币基数取服务端缓存的 total_coins，本局答对即时累加（落库以报告接口为准）
  const [coinTotal, setCoinTotal] = useState<number>(getCachedUser()?.total_coins ?? 0)
  const [explainOpen, setExplainOpen] = useState(true)

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
    setRecords(prev => ({ ...prev, [q.id]: record }))
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
    Taro.redirectTo({ url: '/pages/report/index' })
  }

  const onNext = () => {
    if (!submitted) return
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

      <Text className='quiz-title'>{q.stem}</Text>

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

      {q.type === 'multiple' && !submitted && (
        <View className='confirm-btn' onClick={() => submit(pending)}>
          <Text>确认作答（多选）</Text>
        </View>
      )}

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

      <View className='next'>
        <View className={`prev-btn ${idx === 0 ? 'btn--disabled' : ''}`} onClick={onPrev}>
          <Text>上一题</Text>
        </View>
        <View className={`next-btn ${!submitted ? 'btn--disabled' : ''}`} onClick={onNext}>
          <Text>{isLast ? '查看报告' : '继续'} →</Text>
        </View>
      </View>
    </View>
  )
}
