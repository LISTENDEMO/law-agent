export type AgentName = 'supervisor' | 'legal_research' | 'legal_analysis' | 'critic'

export interface AgentEvent {
  sequence: number
  type: string
  agent: AgentName | null
  summary: string
}

export interface Evidence {
  article_id: string
  law_name: string
  article_number: string
  content: string
  score: number
  retrieval_mode: string
  source_date: string | null
  status: string
}

export interface WorkflowResult {
  status: 'completed' | 'waiting_for_user' | 'insufficient_evidence' | 'budget_exhausted'
  route: 'clarify' | 'simple' | 'complex'
  risk_level: 'low' | 'medium' | 'high'
  answer: string
  clarification: string | null
  evidence: Evidence[]
  analysis: string | null
  agents_executed: AgentName[]
  retry_count: number
  tool_calls: number
  events: AgentEvent[]
}

export interface ChatRun {
  run_id: string
  session_id: string
  events_url: string
  result: WorkflowResult
}

export interface RunState {
  lastSequence: number
  activeAgent: AgentName | null
  events: AgentEvent[]
  completed: boolean
}

