import { ArrowUpRight, CornerDownLeft, LoaderCircle, RotateCcw, Sparkles } from 'lucide-react'

interface ConversationPanelProps {
  query: string
  answer: string
  clarification: string | null
  loading: boolean
  error: string | null
  onQueryChange: (value: string) => void
  onSubmit: () => void
}

const prompts = ['劳动合同违法解除如何计算赔偿？', '民法典关于保证责任有哪些规定？', '公司股权转让需要哪些程序？']

export function ConversationPanel(props: ConversationPanelProps) {
  const hasResult = Boolean(props.answer || props.clarification)
  return (
    <section className="conversation-panel" aria-label="法律咨询对话">
      <div className="panel-kicker"><span>RESEARCH DESK / 01</span><b>事实与问题</b></div>
      <div className="conversation-scroll">
        {!hasResult && !props.loading && (
          <div className="hero-copy">
            <span className="eyebrow"><Sparkles size={13} /> MULTI-AGENT LEGAL RESEARCH</span>
            <h1>把复杂案情，<br />还原成<span>有据可查</span>的<br />结论。</h1>
            <p>由研究、分析与审查 Agent 协作，逐条核验法规来源、版本与适用条件。</p>
            <div className="prompt-grid">
              {prompts.map((prompt, index) => (
                <button key={prompt} type="button" onClick={() => props.onQueryChange(prompt)}>
                  <em>0{index + 1}</em><span>{prompt}</span><ArrowUpRight size={15} />
                </button>
              ))}
            </div>
          </div>
        )}
        {props.loading && (
          <div className="researching-card"><LoaderCircle className="spin" /><div><b>正在组织法律研究</b><span>Supervisor 正在拆解问题并分派专业 Agent</span></div></div>
        )}
        {hasResult && (
          <article className="answer-sheet">
            <header><span>研究意见</span><b>{props.clarification ? '需要补充事实' : '证据校验完成'}</b></header>
            <div className="answer-rule" />
            <p>{props.clarification ?? props.answer}</p>
            <footer>本回答用于法律信息检索与辅助分析，不替代执业律师的正式意见。</footer>
          </article>
        )}
        {props.error && (
          <div className="error-card" role="alert"><b>暂时无法完成研究</b><span>{props.error}</span><button type="button" onClick={props.onSubmit}><RotateCcw size={14} />重新尝试</button></div>
        )}
      </div>
      <div className="composer-shell">
        <textarea
          value={props.query}
          onChange={(event) => props.onQueryChange(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter' && (event.ctrlKey || event.metaKey)) props.onSubmit()
          }}
          placeholder="描述事实、时间与希望解决的问题…"
          rows={3}
        />
        <div className="composer-meta"><span><CornerDownLeft size={13} /> Ctrl + Enter</span><span>请勿输入身份证号等敏感信息</span></div>
        <button className="submit-button" type="button" disabled={props.loading || props.query.trim().length < 2} onClick={props.onSubmit}>开始研究<ArrowUpRight size={16} /></button>
      </div>
    </section>
  )
}
