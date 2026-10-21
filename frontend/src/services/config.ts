// 后端 API 基址由构建模式决定：
// - development 构建读取 .env.development
// - production 构建读取 .env.production
// 只有 TARO_APP_ 前缀的变量会被 Taro 注入客户端
export const API_BASE_URL =
  process.env.TARO_APP_API_BASE_URL || 'http://127.0.0.1:8000'

export const REQUEST_TIMEOUT = 60000
