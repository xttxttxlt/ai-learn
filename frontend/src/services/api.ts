import { request } from './request'
import type { Quiz, QuizGenerateParams, Report, ReportGenerateParams } from '@/types'

export function generateQuiz(params: QuizGenerateParams) {
  return request<Quiz>('/api/v1/quiz/generate', { method: 'POST', data: params })
}

export function generateReport(params: ReportGenerateParams) {
  return request<Report>('/api/v1/report/generate', { method: 'POST', data: params })
}
