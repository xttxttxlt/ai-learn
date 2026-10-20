import type { Source } from '@/types'

export function isKnowledgeBaseSource(source: Source): boolean {
  return source.kind === 'knowledge_base'
}

export function knowledgeBaseMeta(source: Source): string {
  const parts: string[] = []
  if (typeof source.page === 'number' && source.page > 0) {
    parts.push(`第 ${source.page} 页`)
  }
  if (typeof source.score === 'number') {
    parts.push(`相关度 ${Math.round(source.score * 100)}%`)
  }
  return parts.join(' · ')
}
