import { BookOpen, CheckCircle2, ExternalLink } from 'lucide-react'

import type { Evidence, RetrievalMetrics } from '../lib/types'

interface EvidencePanelProps {
  evidence: Evidence[]
  metrics?: RetrievalMetrics | null
  activeId: string | null
  onSelect: (id: string) => void
}

export function EvidencePanel({ evidence, metrics, activeId, onSelect }: EvidencePanelProps) {
  const recallK = metrics?.k ?? 8
  const recallValue = metrics?.recall_at_k == null ? '待评测' : `${Math.round(metrics.recall_at_k * 100)}%`
  const retrievedCount = metrics?.retrieved_count ?? evidence.length

  return (
    <aside className="evidence-panel" aria-label="法规证据" data-lawagent-evidence-panel>
      <div className="panel-kicker"><span>EVIDENCE / 02</span><b>法规证据</b></div>
      <div className="evidence-summary" data-lawagent-evidence-summary>
        <BookOpen className="evidence-summary-icon" size={18} />
        <div>
          <b>{evidence.length || '—'} 条</b>
          <span>已进入回答证据集</span>
        </div>
        <div className="evidence-recall" data-lawagent-recall>
          <b>{recallValue}</b>
          <span>Recall@{recallK}</span>
          <span>命中 {retrievedCount}</span>
        </div>
      </div>
      <div className="evidence-list" data-lawagent-evidence-list>
        {evidence.length === 0 && <div className="empty-rail">提交问题后，引用法条与版本信息将在这里逐条展开。</div>}
        {evidence.map((item, index) => (
          <button className={`evidence-card ${activeId === item.article_id ? 'active' : ''}`} type="button" key={item.article_id} data-testid={`evidence-card-${item.article_id}`} data-lawagent-evidence-card={item.article_id} onClick={() => onSelect(item.article_id)}>
            <span className="evidence-index">0{index + 1}</span>
            <div className="evidence-title"><b>{item.law_name}</b><ExternalLink size={13} /></div>
            <strong>{item.article_number}</strong>
            <p>{item.content}</p>
            <footer><span><CheckCircle2 size={12} />现行有效</span><em>{Math.round(item.score * 100)}% 匹配</em></footer>
          </button>
        ))}
      </div>
    </aside>
  )
}
