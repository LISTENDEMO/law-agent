import type {
  AdminOverview,
  AgentEvent,
  ChatRun,
  RunState,
  RunSummary,
  SessionMessage,
  SessionSummary,
} from './types'

export const initialRunState: RunState = {
  lastSequence: 0,
  activeAgent: null,
  events: [],
  completed: false,
}

export function reduceAgentEvent(state: RunState, event: AgentEvent): RunState {
  if (event.sequence <= state.lastSequence) return state

  let activeAgent = state.activeAgent
  if (event.type === 'agent.started') activeAgent = event.agent
  if (event.type === 'agent.completed' && activeAgent === event.agent) activeAgent = null

  return {
    lastSequence: event.sequence,
    activeAgent,
    events: [...state.events, event],
    completed: event.type === 'run.completed' || event.type === 'run.failed',
  }
}

export async function createChatRun(message: string, sessionId?: string): Promise<ChatRun> {
  const response = await fetch('/api/v1/chat', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ message, session_id: sessionId }),
  })
  if (!response.ok) {
    throw new Error(`咨询请求失败（${response.status}）`)
  }
  return (await response.json()) as ChatRun
}

export interface ChatStreamHandlers {
  onSession?: (sessionId: string) => void
  onAgentEvent?: (event: AgentEvent) => void
  onAnswerDelta?: (delta: string) => void
}

export async function streamChatRun(
  message: string,
  sessionId: string | undefined,
  handlers: ChatStreamHandlers,
): Promise<ChatRun> {
  const response = await fetch('/api/v1/chat/stream', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ message, session_id: sessionId }),
  })
  if (!response.ok) {
    throw new Error(`咨询请求失败（${response.status}）`)
  }
  if (!response.body) {
    throw new Error('当前浏览器不支持流式响应')
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let completed: ChatRun | null = null

  while (true) {
    const { done, value } = await reader.read()
    buffer += decoder.decode(value, { stream: !done })
    let boundary = buffer.indexOf('\n\n')
    while (boundary >= 0) {
      const frame = buffer.slice(0, boundary)
      buffer = buffer.slice(boundary + 2)
      const event = parseSseFrame(frame)
      if (event) {
        if (event.type === 'session.started') {
          const payload = event.data as { session_id?: string }
          if (payload.session_id) handlers.onSession?.(payload.session_id)
        } else if (event.type === 'agent.event') {
          handlers.onAgentEvent?.(event.data as AgentEvent)
        } else if (event.type === 'answer.delta') {
          const payload = event.data as { delta?: string }
          if (payload.delta) handlers.onAnswerDelta?.(payload.delta)
        } else if (event.type === 'chat.completed') {
          completed = event.data as ChatRun
        } else if (event.type === 'chat.error') {
          throw new Error('法律研究执行失败')
        }
      }
      boundary = buffer.indexOf('\n\n')
    }
    if (done) break
  }

  if (!completed) {
    throw new Error('流式响应在完成前中断')
  }
  return completed
}

function parseSseFrame(frame: string): { type: string; data: unknown } | null {
  let type = 'message'
  const dataLines: string[] = []
  for (const line of frame.split('\n')) {
    if (line.startsWith('event:')) type = line.slice(6).trim()
    if (line.startsWith('data:')) dataLines.push(line.slice(5).trimStart())
  }
  if (dataLines.length === 0) return null
  return { type, data: JSON.parse(dataLines.join('\n')) as unknown }
}

export async function listSessions(): Promise<SessionSummary[]> {
  const response = await fetch('/api/v1/sessions')
  if (!response.ok) {
    throw new Error(`历史会话加载失败（${response.status}）`)
  }
  return (await response.json()) as SessionSummary[]
}

export async function getSession(sessionId: string): Promise<SessionMessage[]> {
  const response = await fetch(`/api/v1/sessions/${sessionId}`)
  if (!response.ok) {
    throw new Error(`会话加载失败（${response.status}）`)
  }
  return (await response.json()) as SessionMessage[]
}

export async function getSessionRuns(sessionId: string): Promise<RunSummary[]> {
  const response = await fetch(`/api/v1/sessions/${sessionId}/runs`)
  if (!response.ok) {
    throw new Error(`运行记录加载失败（${response.status}）`)
  }
  return (await response.json()) as RunSummary[]
}

export async function getLatestSessionRun(sessionId: string): Promise<ChatRun | null> {
  const response = await fetch(`/api/v1/sessions/${sessionId}/latest-run`)
  if (response.status === 404) return null
  if (!response.ok) {
    throw new Error(`最近运行加载失败（${response.status}）`)
  }
  return (await response.json()) as ChatRun | null
}

export async function deleteSession(sessionId: string): Promise<void> {
  const response = await fetch(`/api/v1/sessions/${sessionId}`, { method: 'DELETE' })
  if (!response.ok) {
    throw new Error(`会话删除失败（${response.status}）`)
  }
}

export async function getAdminOverview(adminKey: string): Promise<AdminOverview> {
  const response = await fetch('/api/v1/admin/overview', {
    headers: { 'x-admin-key': adminKey },
  })
  if (!response.ok) {
    throw new Error(`后台概览加载失败（${response.status}）`)
  }
  return (await response.json()) as AdminOverview
}

export function subscribeToRun(
  eventsUrl: string,
  onEvent: (event: AgentEvent) => void,
  onError: () => void,
): () => void {
  const stream = new EventSource(eventsUrl)
  const eventTypes = [
    'run.started',
    'agent.started',
    'agent.completed',
    'tool.started',
    'tool.completed',
    'run.completed',
    'run.failed',
  ]
  const handlers = eventTypes.map((eventType) => {
    const handler = (message: MessageEvent<string>) => {
      onEvent(JSON.parse(message.data) as AgentEvent)
      if (eventType === 'run.completed' || eventType === 'run.failed') stream.close()
    }
    stream.addEventListener(eventType, handler as EventListener)
    return [eventType, handler] as const
  })
  stream.onerror = onError

  return () => {
    for (const [eventType, handler] of handlers) {
      stream.removeEventListener(eventType, handler as EventListener)
    }
    stream.close()
  }
}
