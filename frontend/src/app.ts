import { PropsWithChildren } from 'react'
import { useLaunch } from '@tarojs/taro'
import { ensureLogin } from '@/services/auth'

import './app.scss'

function App({ children }: PropsWithChildren<any>) {
  useLaunch(() => {
    // 启动即静默登录；失败不阻塞（匿名模式仍可出题答题）
    ensureLogin()
  })

  // children 是将要会渲染的页面
  return children
}



export default App
