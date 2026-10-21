export type QuestionType = 'single' | 'multiple' | 'judge'
export type Difficulty = 'easy' | 'medium' | 'hard'
export type DifficultyFilter = 'easy' | 'medium' | 'hard' | 'mixed'

export interface Option {
  key: string
  text: string
}

export interface Question {
  id: string
  type: QuestionType
  stem: string
  options: Option[]
  answer: string[]
  explanation: string
  knowledge_point: string
  difficulty: Difficulty
  image_url?: string | null
}

export interface Source {
  title: string
  url: string
  score?: number | null
  kind?: 'search' | 'extract' | 'knowledge_base' | null
  doc_id?: string | null
  chunk_index?: number | null
  page?: number | null
  snippet?: string | null
}

export type KnowledgeDocumentStatus = 'pending' | 'processing' | 'ready' | 'failed'

export interface KnowledgeDocument {
  doc_id: string
  file_name: string
  file_ext: string
  file_size: number
  status: KnowledgeDocumentStatus
  chunk_count: number
  error_message?: string | null
  created_at: string
  finished_at?: string | null
}

export interface KnowledgeBaseStats {
  total_documents: number
  ready_documents: number
  processing_documents: number
  failed_documents: number
  total_chunks: number
}

export interface KnowledgeBaseOverview {
  stats: KnowledgeBaseStats
  documents: KnowledgeDocument[]
}

export interface KnowledgeDocumentList {
  items: KnowledgeDocument[]
  total: number
  page: number
  page_size: number
}

export interface Quiz {
  quiz_id: string
  title: string
  summary: string
  grounded?: boolean
  sources?: Source[]
  questions: Question[]
}

export interface QuizGenerateParams {
  user_input: string
  question_count?: number
  difficulty?: DifficultyFilter
  use_web_search?: boolean
  use_knowledge_base?: boolean
  document_id?: string
  generate_images?: boolean
}

export type QuizJobStatus = 'pending' | 'running' | 'completed' | 'failed'

export interface QuizJobCreateParams extends QuizGenerateParams {
  request_id: string
}

export interface QuizJobCreated {
  job_id: string
  status: QuizJobStatus
}

export interface QuizJob {
  job_id: string
  status: QuizJobStatus
  quiz?: Quiz | null
  error?: string | null
}

export interface AnswerRecord {
  question_id: string
  selected_answers: string[]
  is_correct: boolean
  duration_ms: number
}

export interface Report {
  accuracy: number
  mastered_points: string[]
  weak_points: string[]
  three_line_summary: string[]
  advice: string[]
  share_quote: string
}

export interface ReportGenerateParams {
  quiz_id: string
  topic: string
  questions: Question[]
  answer_records: AnswerRecord[]
}

export interface User {
  id: number
  nickname: string
  avatar_url: string
  total_coins: number
}

export interface ImageQuota {
  usage_date: string
  used: number
  limit: number
  remaining: number
  available: boolean
}

export interface QuizCapabilities {
  web_search: boolean
  knowledge_base: boolean
  image_generation: boolean
}

export interface UserProfile extends User {
  quiz_count: number
  correct_count: number
  average_accuracy: number
  image_quota: ImageQuota
  quiz_capabilities: QuizCapabilities
}

export interface QuizHistoryItem {
  quiz_id: string
  title: string
  accuracy: number | null
  question_count: number | null
  answered_count?: number
  current_index?: number
  created_at: string
}

export interface QuizHistoryList {
  items: QuizHistoryItem[]
  total: number
  page: number
  page_size: number
}

export interface QuizDetail {
  quiz_id: string
  title: string
  summary: string
  created_at: string
  questions: Question[]
  answer_records: AnswerRecord[]
  report: Report | null
  accuracy: number | null
  sources?: Source[]
  grounded?: boolean
  progress?: AnswerRecord[]
  current_index?: number
}
