import { Scale, ShieldCheck } from 'lucide-react'

export function StatusHeader() {
  return (
    <header className="status-header">
      <div className="brand-lockup">
        <span className="brand-seal" aria-hidden="true"><Scale size={19} /></span>
        <div><strong>LawAgent</strong><span>法律研究工作台</span></div>
      </div>
      <div className="system-status"><i /><span>法规索引在线</span><b>45,552</b></div>
      <div className="trust-mark"><ShieldCheck size={15} /><span>证据约束生成</span></div>
    </header>
  )
}
