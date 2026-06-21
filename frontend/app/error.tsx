'use client'

export default function ErrorPage({ reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return <main className="fatal-error"><span>LAWAGENT / ERROR</span><h1>卷宗暂时无法展开</h1><p>页面遇到异常，但你的研究资料仍保存在会话中。</p><button onClick={reset}>重新载入工作台</button></main>
}

