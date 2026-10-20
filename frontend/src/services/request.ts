import Taro from '@tarojs/taro'
import { API_BASE_URL, REQUEST_TIMEOUT } from './config'
import { getToken, relogin } from './auth'

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

/** 后端业务码：4010 = 未登录或登录已过期 */
const CODE_UNAUTHORIZED = 4010

interface RequestOptions {
  method?: 'GET' | 'POST' | 'PUT' | 'DELETE'
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  data?: any
}

async function doRequest<T>(path: string, method: string, data: unknown): Promise<ApiEnvelope<T>> {
  const token = getToken()
  const header: Record<string, string> = { 'Content-Type': 'application/json' }
  if (token) header.Authorization = `Bearer ${token}`
  const res = await Taro.request<ApiEnvelope<T>>({
    url: `${API_BASE_URL}${path}`,
    method: method as keyof Taro.request.Method,
    data,
    header,
    timeout: REQUEST_TIMEOUT
  })
  return res.data
}

/** 统一请求：自动带 token、解包 {code,message,data}，4010 自动重登并重试一次，其余 code!==0 抛 ApiError。 */
export async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = 'GET', data } = options

  let body: ApiEnvelope<T>
  try {
    body = await doRequest<T>(path, method, data)
    if (body && body.code === CODE_UNAUTHORIZED && getToken()) {
      // token 失效：静默重登后重试一次
      const ok = await relogin()
      if (ok) body = await doRequest<T>(path, method, data)
    }
  } catch (e) {
    throw new ApiError(-1, '网络异常，请确认后端服务已启动')
  }

  if (!body || typeof body.code !== 'number') {
    throw new ApiError(-1, '响应格式异常')
  }
  if (body.code !== 0) {
    throw new ApiError(body.code, body.message || '请求失败')
  }
  return body.data
}

function parseUploadBody<T>(raw: unknown): ApiEnvelope<T> {
  if (typeof raw === 'string') {
    try {
      return JSON.parse(raw) as ApiEnvelope<T>
    } catch (e) {
      throw new ApiError(-1, '响应格式异常')
    }
  }
  if (raw && typeof raw === 'object') {
    return raw as ApiEnvelope<T>
  }
  throw new ApiError(-1, '响应格式异常')
}

/** multipart 上传：不设置 JSON Content-Type，自动携带 token 并解包统一响应。 */
export async function uploadFile<T>(
  path: string,
  filePath: string,
  fileName?: string,
  formData?: Record<string, string>
): Promise<T> {
  const doUpload = async (): Promise<ApiEnvelope<T>> => {
    const token = getToken()
    const header: Record<string, string> = {}
    if (token) header.Authorization = `Bearer ${token}`
    const res = await Taro.uploadFile({
      url: `${API_BASE_URL}${path}`,
      filePath,
      name: 'file',
      fileName,
      formData,
      header,
      timeout: REQUEST_TIMEOUT
    })
    return parseUploadBody<T>(res.data)
  }

  let body: ApiEnvelope<T>
  try {
    body = await doUpload()
    if (body && body.code === CODE_UNAUTHORIZED && getToken()) {
      const ok = await relogin()
      if (ok) body = await doUpload()
    }
  } catch (e) {
    if (e instanceof ApiError) throw e
    throw new ApiError(-1, '网络异常，请确认后端服务已启动')
  }

  if (!body || typeof body.code !== 'number') {
    throw new ApiError(-1, '响应格式异常')
  }
  if (body.code !== 0) {
    throw new ApiError(body.code, body.message || '上传失败')
  }
  return body.data
}
