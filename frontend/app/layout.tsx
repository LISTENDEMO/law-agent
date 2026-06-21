import type { Metadata } from 'next'
import '@fontsource-variable/noto-serif-sc'
import '@fontsource-variable/source-sans-3'
import './globals.css'

export const metadata: Metadata = { title: 'LawAgent · 证据优先的法律研究', description: '多 Agent 法律研究与法规溯源工作台' }

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="zh-CN"><head><script src="/lawagent-fallback.js" /></head><body>{children}</body></html>
}
