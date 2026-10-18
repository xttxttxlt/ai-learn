import Taro from '@tarojs/taro'
import { API_BASE_URL, REQUEST_TIMEOUT } from './config'

export interface ApiEnvelope<T> {
  code: number
  message: string
  data: T
}

export class ApiError extends Error {
  code: number
  constructor(code: number, message: string) {
    super(message)
    this.code = code
    this.name = 'ApiError'
  }
}

interface RequestOptions {
  method?: 'GET' | 'POST'
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  data?: any
}

/** 统一请求：自动拼接基址、解包 {code,message,data}，code!==0 抛 ApiError。 */
export async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = 'GET', data } = options

  let res
  try {
    res = await Taro.request<ApiEnvelope<T>>({
      url: `${API_BASE_URL}${path}`,
      method,
      data,
      header: { 'Content-Type': 'application/json' },
      timeout: REQUEST_TIMEOUT
    })
  } catch (e) {
    throw new ApiError(-1, '网络异常，请确认后端服务已启动')
  }

  const body = res.data
  if (!body || typeof body.code !== 'number') {
    throw new ApiError(-1, '响应格式异常')
  }
  if (body.code !== 0) {
    throw new ApiError(body.code, body.message || '请求失败')
  }
  return body.data
}
