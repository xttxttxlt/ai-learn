import Taro from '@tarojs/taro'
import type { AnswerRecord, Quiz } from '@/types'

const CURRENT_QUIZ_KEY = 'ail_current_quiz'
const CURRENT_RECORDS_KEY = 'ail_current_records'

// 与后端 persistence_service.COIN_PER_CORRECT 一致
export const COIN_PER_CORRECT = 10

/* ===== 当前闯关会话（跨页面传递，避免长 URL 传参）===== */
export function setCurrentQuiz(quiz: Quiz) {
  Taro.setStorageSync(CURRENT_QUIZ_KEY, quiz)
}

export function getCurrentQuiz(): Quiz | null {
  const v = Taro.getStorageSync(CURRENT_QUIZ_KEY)
  return v && typeof v === 'object' ? (v as Quiz) : null
}

export function setAnswerRecords(records: AnswerRecord[]) {
  Taro.setStorageSync(CURRENT_RECORDS_KEY, records)
}

export function getAnswerRecords(): AnswerRecord[] {
  const v = Taro.getStorageSync(CURRENT_RECORDS_KEY)
  return Array.isArray(v) ? (v as AnswerRecord[]) : []
}

/* ===== 日期格式化（历史记录展示用）===== */
/** 后端 "2026-10-19 10:00:00" -> "10 月 19 日"；解析失败原样返回。 */
export function formatHistoryDate(s: string): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(s)
  if (!m) return s
  return `${Number(m[2])} 月 ${Number(m[3])} 日`
}
