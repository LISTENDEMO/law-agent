import type { AgentEvent, ChatRun, RunState } from './types'

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
