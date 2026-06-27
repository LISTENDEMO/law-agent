'use client'

import { useEffect, useMemo, useState } from 'react'

import { History, MessageSquarePlus, Trash2, X } from 'lucide-react'

import { deleteSession, getLatestSessionRun, getSession, listSessions, streamChatRun } from '../lib/api'
import type { AgentEvent, ChatRun, ConversationMessage, SessionSummary } from '../lib/types'
import { ConversationPanel } from './ConversationPanel'
import { EvidencePanel } from './EvidencePanel'
import { StatusHeader } from './StatusHeader'
import { TraceRail } from './TraceRail'

type Panel = 'chat' | 'evidence' | 'trace'

export function LegalWorkspace() {
  const [query, setQuery] = useState('')
  const [run, setRun] = useState<ChatRun | null>(null)
  const [events, setEvents] = useState<AgentEvent[]>([])
  const [messages, setMessages] = useState<ConversationMessage[]>([])
  const [sessions, setSessions] = useState<SessionSummary[]>([])
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [historyLoading, setHistoryLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [panel, setPanel] = useState<Panel>('chat')
  const [activeEvidence, setActiveEvidence] = useState<string | null>(null)
  const [historyOpen, setHistoryOpen] = useState(false)

  useEffect(() => {
    const readyWindow = window as Window & { __lawagentReactReady?: boolean }
    readyWindow.__lawagentReactReady = true
    void refreshSessions()
    return () => {
      readyWindow.__lawagentReactReady = false
    }
  }, [])

  const result = run?.result
  const agents = useMemo(() => result?.agents_executed ?? [], [result])

  async function refreshSessions() {
    try {
      setSessions(await listSessions())
    } catch {
      setSessions([])
    }
  }

  async function selectSession(sessionId: string) {
    setHistoryLoading(true)
    setError(null)
    try {
      const [sessionMessages, latestRun] = await Promise.all([
        getSession(sessionId),
        getLatestSessionRun(sessionId),
      ])
      setActiveSessionId(sessionId)
      setMessages(
        sessionMessages.map((message, index) => ({
          id: `${sessionId}-${index}`,
          role: message.role,
          content: message.content,
          status: 'done',
          structuredAnswer: message.structured_answer,
        })),
      )
      setRun(latestRun)
      setEvents(latestRun?.result.events ?? [])
      setActiveEvidence(null)
      setQuery('')
      setPanel('chat')
      setHistoryOpen(false)
    } catch {
      setError('历史会话加载失败，请稍后重试。')
    } finally {
      setHistoryLoading(false)
    }
  }

  function startNewSession() {
    setActiveSessionId(null)
    setRun(null)
    setEvents([])
    setMessages([])
    setActiveEvidence(null)
    setQuery('')
    setPanel('chat')
    setError(null)
    setHistoryOpen(false)
  }

  async function removeSession(sessionId: string) {
    setError(null)
    try {
      await deleteSession(sessionId)
      setSessions((current) => current.filter((session) => session.id !== sessionId))
      if (activeSessionId === sessionId) startNewSession()
    } catch {
      setError('历史会话删除失败，请稍后重试。')
    }
  }

  async function submit(value?: string) {
    const submittedQuery = (value ?? query).trim()
    if (submittedQuery.length < 2 || loading) return
    setLoading(true)
    setError(null)
    setQuery('')
    const assistantId = createMessageId('assistant')
    setMessages((current) => [
      ...current,
      { id: createMessageId('user'), role: 'user', content: submittedQuery, status: 'done' },
      { id: assistantId, role: 'assistant', content: '', status: 'streaming' },
    ])
    setEvents([])
    try {
      const nextRun = await streamChatRun(submittedQuery, activeSessionId ?? undefined, {
        onSession: setActiveSessionId,
        onAgentEvent: (event) =>
          setEvents((current) =>
            current.some((item) => item.sequence === event.sequence) ? current : [...current, event],
          ),
        onAnswerDelta: (delta) =>
          setMessages((current) =>
            current.map((message) =>
              message.id === assistantId
                ? { ...message, content: `${message.content}${delta}` }
                : message,
            ),
          ),
      })
      setRun(nextRun)
      setActiveSessionId(nextRun.session_id)
      setMessages((current) =>
        current.map((message) =>
          message.id === assistantId
            ? {
                ...message,
                content: message.content || nextRun.result.clarification || nextRun.result.answer,
                status: 'done',
                structuredAnswer: nextRun.result.structured_answer,
              }
            : message,
        ),
      )
      await refreshSessions()
    } catch {
      setError('请检查后端服务和网络连接后重试。')
      setMessages((current) =>
        current.map((message) =>
          message.id === assistantId
            ? {
                ...message,
                content:
                  message.content || '这次请求没有完成。你可以直接点“重新尝试”，我会保留当前问题。',
                status: 'error',
              }
            : message,
        ),
      )
    } finally {
      setLoading(false)
    }
  }

  function selectEvidence(id: string) {
    setActiveEvidence(id)
    setPanel('evidence')
  }

  return (
    <main className="app-shell">
      <StatusHeader />
      <div className="mobile-command-bar">
        <button
          className="mobile-history-trigger"
          type="button"
          aria-label="打开历史会话"
          aria-expanded={historyOpen}
          onClick={() => setHistoryOpen(true)}
        >
          <History size={15} />
          历史
        </button>
        <nav className="mobile-tabs" role="tablist" aria-label="工作台面板">
          {([['chat', '对话'], ['evidence', '证据'], ['trace', '轨迹']] as const).map(([value, label]) => (
          <button
            key={value}
            role="tab"
            data-lawagent-tab={value}
            aria-selected={panel === value}
            onClick={() => setPanel(value)}
          >
            {label}
          </button>
          ))}
        </nav>
      </div>
      <button
        className="mobile-history-scrim"
        type="button"
        aria-label="关闭历史会话"
        data-open={historyOpen}
        onClick={() => setHistoryOpen(false)}
      />
      <div className="workspace-grid">
        <HistoryPanel
          sessions={sessions}
          activeSessionId={activeSessionId}
          loading={historyLoading}
          onNewSession={startNewSession}
          onSelectSession={selectSession}
          onDeleteSession={removeSession}
          mobileOpen={historyOpen}
          onClose={() => setHistoryOpen(false)}
        />
        <div className={panel === 'chat' ? 'mobile-active' : ''} data-lawagent-panel="chat">
          <ConversationPanel
            query={query}
            messages={messages}
            evidence={result?.evidence ?? []}
            loading={loading}
            error={error}
            onQueryChange={setQuery}
            onSubmit={submit}
            onCitationSelect={selectEvidence}
          />
        </div>
        <div className={panel === 'evidence' ? 'mobile-active' : ''} data-lawagent-panel="evidence">
          <EvidencePanel
            evidence={result?.evidence ?? []}
            metrics={result?.retrieval_metrics ?? null}
            activeId={activeEvidence}
            onSelect={selectEvidence}
          />
        </div>
        <div className={panel === 'trace' ? 'mobile-active' : ''} data-lawagent-panel="trace">
          <TraceRail events={events} agents={agents} />
        </div>
      </div>
      <footer className="global-footer">
        <span>LAWAGENT / EVIDENCE-FIRST LEGAL INTELLIGENCE</span>
        <span>中国大陆法律法规 · 更新于 2026.06</span>
      </footer>
    </main>
  )
}

function HistoryPanel({
  sessions,
  activeSessionId,
  loading,
  onNewSession,
  onSelectSession,
  onDeleteSession,
  mobileOpen,
  onClose,
}: {
  sessions: SessionSummary[]
  activeSessionId: string | null
  loading: boolean
  onNewSession: () => void
  onSelectSession: (sessionId: string) => void
  onDeleteSession: (sessionId: string) => void
  mobileOpen: boolean
  onClose: () => void
}) {
  return (
    <aside
      className="history-panel"
      aria-label="历史会话"
      data-testid="mobile-history-drawer"
      data-open={mobileOpen}
      aria-hidden={!mobileOpen ? undefined : false}
    >
      <div className="panel-kicker">
        <span>HISTORY / 00</span>
        <b>会话数据库</b>
        <button className="mobile-history-close" type="button" aria-label="关闭历史会话" onClick={onClose}>
          <X size={15} />
        </button>
      </div>
      <button className="new-session-button" type="button" onClick={onNewSession}>
        <MessageSquarePlus size={15} />
        新建对话
      </button>
      <div className="history-list" data-lawagent-history-list>
        {loading && <div className="empty-rail">正在载入历史会话…</div>}
        {!loading && sessions.length === 0 && <div className="empty-rail">还没有历史记录，完成一次研究后会自动归档。</div>}
        {sessions.map((session) => (
          <article
            className={`history-item ${activeSessionId === session.id ? 'active' : ''}`}
            key={session.id}
            data-lawagent-session-id={session.id}
          >
            <button
              className="history-select"
              type="button"
              aria-label={session.title}
              onClick={() => onSelectSession(session.id)}
            >
              <b>{session.title}</b>
              <span>{session.last_message || '暂无回答'}</span>
              <em>
                {session.message_count} 条消息 · {session.run_count} 次运行
              </em>
            </button>
            <button
              className="history-delete"
              type="button"
              aria-label={`删除会话 ${session.title}`}
              onClick={() => onDeleteSession(session.id)}
            >
              <Trash2 size={13} />
            </button>
          </article>
        ))}
      </div>
    </aside>
  )
}

function createMessageId(prefix: string) {
  return `${prefix}-${Date.now()}-${Math.random().toString(16).slice(2)}`
}
