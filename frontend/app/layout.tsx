import type { Metadata } from 'next'
// 高级字体组合：思源宋体 + 思源黑体 + LXGW WenKai（霞鹜文楷）
import '@fontsource-variable/noto-serif-sc'
import '@fontsource-variable/noto-sans-sc'
import '@fontsource/lxgw-wenkai'
import './globals.css'

export const metadata: Metadata = {
  title: 'LawAgent · 法律研究工作台',
  description: '基于证据的法律研究与法规溯源系统',
}

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  )
}