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
  structured_answer?: StructuredAnswer | null
  retrieval_metrics?: RetrievalMetrics | null
}

export interface StructuredAnswer {
  summary: string
  key_points: string[]
  analysis: string | null
  citations: string[]
  notice: string
}

export interface RetrievalMetrics {
  k: number
  retrieved_count: number
  recall_at_k: number | null
  status: 'pending_gold' | 'evaluated'
}

export interface ChatRun {
  run_id: string
  session_id: string
  events_url: string
  result: WorkflowResult
}

export interface SessionSummary {
  id: string
  title: string
  last_message: string
  created_at: string
  updated_at: string
  message_count: number
  run_count: number
}

export interface SessionMessage {
  role: 'user' | 'assistant'
  content: string
  created_at: string
  structured_answer?: StructuredAnswer | null
}

export interface RunSummary {
  id: string
  query: string
  status: WorkflowResult['status']
  route: WorkflowResult['route']
  risk_level: WorkflowResult['risk_level']
  created_at: string
  agents_executed: AgentName[]
  evidence_count: number
}

export interface AdminOverview {
  corpus: {
    status: string
    report_url: string
    report?: {
      total_files?: number
      accepted?: number
      article_count?: number
    }
  }
  index: {
    status: string
    metadata: {
      embedding_model?: string
      article_count?: number
      dimension?: number
    } | null
  }
  recent_runs: RunSummary[]
  evaluation: {
    open_ended_case_count: number
    categories: string[]
  }
}

export interface ConversationMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  status?: 'streaming' | 'done' | 'error'
  structuredAnswer?: StructuredAnswer | null
}

export interface RunState {
  lastSequence: number
  activeAgent: AgentName | null
  events: AgentEvent[]
  completed: boolean
}
