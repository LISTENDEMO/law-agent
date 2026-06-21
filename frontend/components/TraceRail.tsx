import { BrainCircuit, Check, Circle, Search, ShieldCheck } from 'lucide-react'

import type { AgentEvent, AgentName } from '../lib/types'

const labels: Record<AgentName, [string, string]> = {
  supervisor: ['任务监督员', '规划与动态委派'],
  legal_research: ['法律研究员', '混合检索与版本过滤'],
  legal_analysis: ['要件分析员', '事实与法律要件映射'],
  critic: ['独立审查员', '证据覆盖与风险审查'],
}

const icons = { supervisor: BrainCircuit, legal_research: Search, legal_analysis: Circle, critic: ShieldCheck }

interface TraceRailProps { events: AgentEvent[]; agents: AgentName[] }

export function TraceRail({ events, agents }: TraceRailProps) {
  return (
    <aside className="trace-panel" aria-label="Agent 执行轨迹" data-lawagent-trace-panel>
      <div className="panel-kicker"><span>TRACE / 03</span><b>Agent 协作</b></div>
      <div className="trace-list">
        {(agents.length ? agents : (Object.keys(labels) as AgentName[])).map((agent, index) => {
          const Icon = icons[agent]
          const done = agents.includes(agent)
          return <div className={`agent-node ${done ? 'done' : ''}`} key={agent}><div className="agent-line"><i>{done ? <Check size={12} /> : index + 1}</i></div><span className="agent-icon"><Icon size={17} /></span><div><b>{labels[agent][0]}</b><span>{labels[agent][1]}</span></div>{done && <em>完成</em>}</div>
        })}
      </div>
      <div className="event-log" data-lawagent-event-log><header><span>运行日志</span><b>{events.length} EVENTS</b></header>{events.slice(-5).map((event) => <div key={event.sequence}><time>{String(event.sequence).padStart(2, '0')}</time><p>{event.summary}</p></div>)}</div>
    </aside>
  )
}
