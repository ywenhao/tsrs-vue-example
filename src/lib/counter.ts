const formatter = new Intl.NumberFormat('zh-CN')

export function formatCount(value: number): string {
  return formatter.format(value)
}
