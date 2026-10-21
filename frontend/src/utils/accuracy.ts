const RED = '#e5534b'
const YELLOW = '#e6a817'
const GREEN = '#2fb344'

export function accuracyColor(percent: number): string {
  if (percent >= 90) return GREEN
  if (percent >= 60) return YELLOW
  return RED
}
