'use client'

import { useEffect, useMemo, useState } from 'react'

import { createChatRun, subscribeToRun } from '../lib/api'
import type { AgentEvent, ChatRun } from '../lib/types'
import { ConversationPanel } from './ConversationPanel'
import { EvidencePanel } from './EvidencePanel'
import { StatusHeader } from './StatusHeader'
import { TraceRail } from './TraceRail'

type Panel = 'chat' | 'evidence' | 'trace'

export function LegalWorkspace() {
  const [query, setQuery] = useState('')
  const [run, setRun] = useState<ChatRun | null>(null)
  const [events, setEvents] = useState<AgentEvent[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [panel, setPanel] = useState<Panel>('chat')
  const [activeEvidence, setActiveEvidence] = useState<string | null>(null)

  useEffect(() => {
    if (!run) return
    return subscribeToRun(run.events_url, (event) => setEvents((current) => current.some((item) => item.sequence === event.sequence) ? current : [...current, event]), () => setError('执行轨迹连接中断，最终研究结果仍已保留。'))
  }, [run])

  const result = run?.result
  const agents = useMemo(() => result?.agents_executed ?? [], [result])

  async function submit(value?: string) {
    const submittedQuery = (value ?? query).trim()
    if (submittedQuery.length < 2 || loading) return
    setLoading(true); setError(null); setEvents([])
    try {
      const nextRun = await createChatRun(submittedQuery, run?.session_id)
      setRun(nextRun); setEvents(nextRun.result.events)
      setActiveEvidence(nextRun.result.evidence[0]?.article_id ?? null)
    } catch {
      setError('请检查后端服务和网络连接后重试。')
    } finally { setLoading(false) }
  }

  return (
    <main className="app-shell">
      <StatusHeader />
      <nav className="mobile-tabs" role="tablist" aria-label="工作台面板">
        {([['chat', '对话'], ['evidence', '证据'], ['trace', '轨迹']] as const).map(([value, label]) => <button key={value} role="tab" data-lawagent-tab={value} aria-selected={panel === value} onClick={() => setPanel(value)}>{label}</button>)}
      </nav>
      <div className="workspace-grid">
        <div className={panel === 'chat' ? 'mobile-active' : ''} data-lawagent-panel="chat"><ConversationPanel query={query} answer={result?.answer ?? ''} clarification={result?.clarification ?? null} loading={loading} error={error} onQueryChange={setQuery} onSubmit={submit} /></div>
        <div className={panel === 'evidence' ? 'mobile-active' : ''} data-lawagent-panel="evidence"><EvidencePanel evidence={result?.evidence ?? []} activeId={activeEvidence} onSelect={setActiveEvidence} /></div>
        <div className={panel === 'trace' ? 'mobile-active' : ''} data-lawagent-panel="trace"><TraceRail events={events} agents={agents} /></div>
      </div>
      <footer className="global-footer"><span>LAWAGENT / EVIDENCE-FIRST LEGAL INTELLIGENCE</span><span>中国大陆法律法规 · 更新于 2026.06</span></footer>
    </main>
  )
}
