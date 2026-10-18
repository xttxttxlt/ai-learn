import Taro from '@tarojs/taro'
import type { AnswerRecord, Quiz } from '@/types'

const COIN_KEY = 'ail_coins'
const HISTORY_KEY = 'ail_history'
const CURRENT_QUIZ_KEY = 'ail_current_quiz'
const CURRENT_RECORDS_KEY = 'ail_current_records'

// 原型首页初始显示 602 金币；历史记录首屏与原型一致（首次运行时种子数据）。
export const DEFAULT_COINS = 602
export const COIN_PER_CORRECT = 10

export interface HistoryItem {
  quiz_id: string
  title: string
  date: string
  mastery: number
}

const SEED_HISTORY: HistoryItem[] = [
  { quiz_id: 'seed_math', title: '数学闯关', date: '10 月 15 日', mastery: 60 },
  { quiz_id: 'seed_science', title: '科学闯关', date: '10 月 12 日', mastery: 40 }
]

/* ===== 金币 ===== */
export function getCoins(): number {
  const v = Taro.getStorageSync(COIN_KEY)
  return typeof v === 'number' ? v : DEFAULT_COINS
}

export function addCoins(n: number): number {
  const next = getCoins() + n
  Taro.setStorageSync(COIN_KEY, next)
  return next
}

/* ===== 历史记录 ===== */
export function getHistory(): HistoryItem[] {
  const v = Taro.getStorageSync(HISTORY_KEY)
  if (Array.isArray(v)) return v as HistoryItem[]
  // 首次运行：写入与原型一致的种子数据
  Taro.setStorageSync(HISTORY_KEY, SEED_HISTORY)
  return SEED_HISTORY
}

export function pushHistory(item: HistoryItem): HistoryItem[] {
  // 按 quiz_id 去重，避免重复进入报告页时写入多条
  const rest = getHistory().filter(h => h.quiz_id !== item.quiz_id)
  const list = [item, ...rest].slice(0, 20)
  Taro.setStorageSync(HISTORY_KEY, list)
  return list
}

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

/* ===== 日期格式化（用于历史记录）===== */
export function formatDate(d: Date = new Date()): string {
  return `${d.getMonth() + 1} 月 ${d.getDate()} 日`
}
