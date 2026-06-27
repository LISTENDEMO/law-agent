'use client'

import type { ReactNode } from 'react'
import { useState } from 'react'

import { Activity, Database, FileStack, Gauge, ShieldCheck } from 'lucide-react'

import { getAdminOverview } from '../lib/api'
import type { AdminOverview } from '../lib/types'

export function AdminDashboard() {
  const [adminKey, setAdminKey] = useState('')
  const [overview, setOverview] = useState<AdminOverview | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function loadOverview() {
    if (!adminKey.trim() || loading) return
    setLoading(true)
    setError(null)
    try {
      setOverview(await getAdminOverview(adminKey.trim()))
    } catch {
      setError('后台状态加载失败，请检查 Admin Token。')
    } finally {
      setLoading(false)
    }
  }

  return (
    <main className="admin-shell">
      <section className="admin-hero">
        <span>
          <ShieldCheck size={14} /> LAWAGENT ADMIN
        </span>
        <h1>后台运行态看板</h1>
        <p>用于面试演示语料、索引、最近运行和开放式评测状态。所有后台接口都需要 Admin Token。</p>
        <div className="admin-auth">
          <label>
            Admin Token
            <input
              aria-label="Admin Token"
              value={adminKey}
              onChange={(event) => setAdminKey(event.target.value)}
              placeholder="输入 LAWAGENT_ADMIN_API_KEY"
              type="password"
            />
          </label>
          <button type="button" onClick={loadOverview} disabled={loading}>
            {loading ? '加载中…' : '加载后台状态'}
          </button>
        </div>
        {error && <div className="admin-error" role="alert">{error}</div>}
      </section>

      {overview && (
        <section className="admin-grid" aria-label="后台概览">
          <MetricCard
            icon={<FileStack size={18} />}
            label="语料文件"
            value={formatNumber(overview.corpus.report?.total_files)}
            note={`${overview.corpus.status} · accepted ${formatNumber(overview.corpus.report?.accepted)}`}
          />
          <MetricCard
            icon={<Database size={18} />}
            label="索引法条"
            value={formatNumber(overview.index.metadata?.article_count)}
            note={`${overview.index.status} · ${overview.index.metadata?.dimension ?? '—'} dims`}
          />
          <MetricCard
            icon={<Gauge size={18} />}
            label="开放评测"
            value={formatNumber(overview.evaluation.open_ended_case_count)}
            note={overview.evaluation.categories.join(' / ')}
          />
          <MetricCard
            icon={<Activity size={18} />}
            label="最近运行"
            value={formatNumber(overview.recent_runs.length)}
            note="数据库持久化会话"
          />
          <div className="admin-card admin-runs">
            <header>
              <span>RECENT RUNS</span>
              <b>最近运行记录</b>
            </header>
            {overview.recent_runs.length === 0 && <p>暂无运行记录。</p>}
            {overview.recent_runs.map((run) => (
              <article key={run.id}>
                <b>{run.query}</b>
                <span>
                  {run.status} · {run.route} · {run.risk_level} · {run.evidence_count} 条证据
                </span>
              </article>
            ))}
          </div>
        </section>
      )}
    </main>
  )
}

function MetricCard({
  icon,
  label,
  value,
  note,
}: {
  icon: ReactNode
  label: string
  value: string
  note: string
}) {
  return (
    <div className="admin-card">
      <i>{icon}</i>
      <span>{label}</span>
      <strong>{value}</strong>
      <em>{note}</em>
    </div>
  )
}

function formatNumber(value: number | undefined) {
  return typeof value === 'number' ? value.toLocaleString('en-US') : '—'
}
