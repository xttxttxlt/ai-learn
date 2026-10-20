import { request, uploadFile } from './request'
import type {
  AnswerRecord,
  KnowledgeBaseOverview,
  KnowledgeDocument,
  QuizJob,
  QuizJobCreated,
  QuizJobCreateParams,
  Report,
  ReportGenerateParams,
  UserProfile,
  QuizHistoryList,
  QuizDetail
} from '@/types'

export function createQuizJob(params: QuizJobCreateParams) {
  return request<QuizJobCreated>('/api/v1/quiz/jobs', { method: 'POST', data: params })
}

export function getQuizJob(jobId: string) {
  return request<QuizJob>(`/api/v1/quiz/jobs/${jobId}`)
}

export function saveQuizProgress(params: { quiz_id: string; index: number; records: AnswerRecord[] }) {
  return request<null>('/api/v1/quiz/progress', { method: 'POST', data: params })
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

export function getKnowledgeBase() {
  return request<KnowledgeBaseOverview>('/api/v1/knowledge-base')
}

export function uploadKnowledgeDocument(filePath: string, fileName: string) {
  // 小程序 uploadFile 会用临时路径作为文件名，额外用表单字段传真实文件名
  return uploadFile<KnowledgeDocument>('/api/v1/knowledge-base/documents', filePath, fileName, {
    file_name: fileName
  })
}

export function deleteKnowledgeDocument(docId: string) {
  return request<null>(`/api/v1/knowledge-base/documents/${docId}`, { method: 'DELETE' })
}
