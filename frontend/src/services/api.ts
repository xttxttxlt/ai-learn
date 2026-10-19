import { request } from './request'
import type {
  Quiz,
  QuizGenerateParams,
  Report,
  ReportGenerateParams,
  UserProfile,
  QuizHistoryList,
  QuizDetail
} from '@/types'

export function generateQuiz(params: QuizGenerateParams) {
  return request<Quiz>('/api/v1/quiz/generate', { method: 'POST', data: params })
}

export function generateReport(params: ReportGenerateParams) {
  return request<Report>('/api/v1/report/generate', { method: 'POST', data: params })
}

export function getProfile() {
  return request<UserProfile>('/api/v1/user/profile')
}

export function updateProfile(params: { nickname?: string; avatar_url?: string }) {
  return request<UserProfile>('/api/v1/user/profile', { method: 'PUT', data: params })
}

export function getQuizHistory(page = 1, pageSize = 10) {
  return request<QuizHistoryList>(`/api/v1/user/quizzes?page=${page}&page_size=${pageSize}`)
}

export function getQuizDetail(quizId: string) {
  return request<QuizDetail>(`/api/v1/user/quizzes/${quizId}`)
}
