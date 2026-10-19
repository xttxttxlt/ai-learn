import Taro from '@tarojs/taro'
import { API_BASE_URL, REQUEST_TIMEOUT } from './config'
import type { User } from '@/types'

const TOKEN_KEY = 'ail_token'
const USER_KEY = 'ail_user'

let loginPromise: Promise<boolean> | null = null

export function getToken(): string {
  const v = Taro.getStorageSync(TOKEN_KEY)
  return typeof v === 'string' ? v : ''
}

export function setToken(token: string) {
  Taro.setStorageSync(TOKEN_KEY, token)
}

export function getCachedUser(): User | null {
  const v = Taro.getStorageSync(USER_KEY)
  return v && typeof v === 'object' ? (v as User) : null
}

export function setCachedUser(user: User) {
  Taro.setStorageSync(USER_KEY, user)
}

export function clearAuth() {
  Taro.removeStorageSync(TOKEN_KEY)
  Taro.removeStorageSync(USER_KEY)
}

/** 静默登录：Taro.login 拿 code -> 后端换 token；失败返回 false（不抛异常，匿名可继续用）。 */
async function silentLogin(): Promise<boolean> {
  try {
    const loginRes = await Taro.login()
    if (!loginRes.code) return false
    const res = await Taro.request<{ code: number; message: string; data: { token: string; user: User } }>({
      url: `${API_BASE_URL}/api/v1/user/login`,
      method: 'POST',
      data: { code: loginRes.code },
      header: { 'Content-Type': 'application/json' },
      timeout: REQUEST_TIMEOUT
    })
    const body = res.data
    if (!body || body.code !== 0 || !body.data?.token) return false
    setToken(body.data.token)
    setCachedUser(body.data.user)
    return true
  } catch (e) {
    return false
  }
}

/** 确保已登录：本地有 token 直接通过；否则静默登录（并发去重）。 */
export function ensureLogin(): Promise<boolean> {
  if (getToken()) return Promise.resolve(true)
  if (!loginPromise) {
    loginPromise = silentLogin().finally(() => {
      loginPromise = null
    })
  }
  return loginPromise
}

/** 401 后强制重新登录（清 token 再静默登录）。 */
export function relogin(): Promise<boolean> {
  clearAuth()
  return ensureLogin()
}
