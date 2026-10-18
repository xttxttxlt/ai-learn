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
}

export interface Quiz {
  quiz_id: string
  title: string
  summary: string
  questions: Question[]
}

export interface QuizGenerateParams {
  user_input: string
  question_count?: number
  difficulty?: DifficultyFilter
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
