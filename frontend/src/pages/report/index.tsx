import { useState } from 'react'
import { View, Text } from '@tarojs/components'
import Taro, { useLoad } from '@tarojs/taro'
import CoinPill from '@/components/CoinPill'
import ProgressRing from '@/components/ProgressRing'
import TabBar from '@/components/TabBar'
import { generateReport } from '@/services/api'
import { ApiError } from '@/services/request'
import {
  COIN_PER_CORRECT,
  formatDate,
  getAnswerRecords,
  getCurrentQuiz,
  pushHistory
} from '@/store'
import type { Report } from '@/types'
import './index.scss'

export default function ReportPage() {
  const [report, setReport] = useState<Report | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [topic, setTopic] = useState('本次学习')
  const [earned, setEarned] = useState(0)
  const [wrongCount, setWrongCount] = useState(0)

  const load = async () => {
    const quiz = getCurrentQuiz()
    const records = getAnswerRecords()
    setTopic(quiz?.title || '本次学习')
    setEarned(records.filter(r => r.is_correct).length * COIN_PER_CORRECT)
    setWrongCount(records.filter(r => !r.is_correct).length)

    if (!quiz || records.length === 0) {
      setLoading(false)
      setError('缺少答题数据，请重新闯关')
      return
    }
    setLoading(true)
    setError('')
    try {
      const r = await generateReport({
        quiz_id: quiz.quiz_id,
        topic: quiz.title,
        questions: quiz.questions,
        answer_records: records
      })
      setReport(r)
      pushHistory({ quiz_id: quiz.quiz_id, title: quiz.title, date: formatDate(), mastery: r.accuracy })
    } catch (e) {
      setError(e instanceof ApiError ? e.message : '报告生成失败，请重试')
    } finally {
      setLoading(false)
    }
  }

  useLoad(() => {
    load()
  })

  if (loading) {
    return (
      <View className='page state'>
        <View className='state__spinner' />
        <Text className='state__text'>AI 正在生成复盘报告…</Text>
      </View>
    )
  }

  if (error || !report) {
    return (
      <View className='page state'>
        <Text className='state__text'>{error || '报告加载失败'}</Text>
        <View className='state__btn' onClick={load}>
          <Text>重试</Text>
        </View>
        <View className='state__btn state__btn--ghost' onClick={() => Taro.reLaunch({ url: '/pages/index/index' })}>
          <Text>返回首页</Text>
        </View>
      </View>
    )
  }

  const r = report
  const headline = r.accuracy >= 80 ? '你这局学得很稳' : r.accuracy >= 60 ? '不错，稳步前进' : '别灰心，再闯一次'

  return (
    <View className='page'>
      <View className='toolbar'>
        <Text className='toolbar__topic'>{topic}</Text>
        <CoinPill value={earned} prefix='+' />
      </View>

      <Text className='headline'>{headline}</Text>
      <Text className='subtitle'>先看结果，再看错因，最后给你下一步建议。</Text>

      <View className='badges'>
        <View className='badge badge--green'>
          <View className='icon icon-star badge__icon' />
          <Text>掌握 +{r.mastered_points.length}</Text>
        </View>
        <View className='badge badge--red'>
          <View className='icon icon-chart badge__icon' />
          <Text>错题 {wrongCount}</Text>
        </View>
      </View>

      {/* 掌握度 + 三句总结 */}
      <View className='note-card'>
        <View className='card-h'>
          <View className='icon icon-clock card-h__icon' />
          <Text className='card-h__title'>掌握度</Text>
        </View>
        <View className='mastery'>
          <ProgressRing percent={r.accuracy} size='lg' color='#ff7a2f' />
          <View className='mastery__right'>
            {r.three_line_summary.map((line, i) => (
              <Text className='mastery__line' key={i}>
                {line}
              </Text>
            ))}
            <View className='mastery__bar'>
              <View className='mastery__bar-fill' style={{ width: `${r.accuracy}%` }} />
            </View>
          </View>
        </View>
      </View>

      {/* 掌握得好的点 */}
      {r.mastered_points.length > 0 && (
        <View className='note-card'>
          <View className='card-h'>
            <View className='icon icon-star card-h__icon' />
            <Text className='card-h__title'>掌握得好的点</Text>
          </View>
          <View className='chips'>
            {r.mastered_points.map((p, i) => (
              <View className='chip chip--green' key={i}>
                <Text>{p}</Text>
              </View>
            ))}
          </View>
        </View>
      )}

      {/* 最该补的点 */}
      <View className='note-card'>
        <View className='card-h'>
          <View className='icon icon-warning card-h__icon' />
          <Text className='card-h__title'>最该补的 {r.weak_points.length} 点</Text>
        </View>
        {r.weak_points.length > 0 ? (
          r.weak_points.map((p, i) => (
            <Text className='list-line' key={i}>
              {i + 1}. {p}
            </Text>
          ))
        ) : (
          <Text className='list-line'>全部掌握，太棒了！</Text>
        )}
      </View>

      {/* 复习建议 */}
      {r.advice.length > 0 && (
        <View className='note-card'>
          <View className='card-h'>
            <View className='icon icon-warning card-h__icon' />
            <Text className='card-h__title'>复习建议</Text>
          </View>
          {r.advice.map((a, i) => (
            <View className='advice' key={i}>
              <View className='advice__num'>
                <Text>{i + 1}</Text>
              </View>
              <Text className='advice__text'>{a}</Text>
            </View>
          ))}
        </View>
      )}

      {/* 分享海报（仅预览 UI） */}
      <View className='sticker'>
        <View className='card-h'>
          <View className='icon icon-share card-h__icon' />
          <Text className='card-h__title'>分享海报</Text>
        </View>
        <View className='poster'>
          <Text className='poster__quote'>{r.share_quote}</Text>
          <View className='poster__qr' />
        </View>
      </View>

      <View className='actions'>
        <View className='btn-primary' onClick={() => Taro.reLaunch({ url: '/pages/index/index' })}>
          <Text>再来一组</Text>
        </View>
        <View
          className='btn-ghost'
          onClick={() => Taro.showToast({ title: '海报生成开发中，敬请期待', icon: 'none' })}
        >
          <Text>生成海报</Text>
        </View>
      </View>

      <TabBar active='profile' />
    </View>
  )
}
