import { useEffect, useMemo, useRef, useState } from 'react'

import {
  ArrowUpRight,
  Clipboard,
  FileCheck2,
  CornerDownLeft,
  Download,
  ListChecks,
  LoaderCircle,
  RotateCcw,
  Scale,
  Send,
  ShieldAlert,
} from 'lucide-react'

import type { ConversationMessage, Evidence, StructuredAnswer } from '../lib/types'

interface ConversationPanelProps {
  query: string
  messages: ConversationMessage[]
  evidence: Evidence[]
  loading: boolean
  error: string | null
  onQueryChange: (value: string) => void
  onSubmit: (value?: string) => void
  onCitationSelect: (id: string) => void
}

const prompts = [
  '劳动合同违法解除如何计算赔偿？',
  '民法典关于保证责任有哪些规定？',
  '公司股权转让需要哪些程序？',
  '借款到期后诉讼时效怎么计算？',
  '房屋买卖合同解除后定金能否退还？',
  '交通事故误工费和护理费如何主张？',
  '试用期被辞退是否需要经济补偿？',
  '夫妻共同债务如何认定？',
  '公司拖欠工资可以主张哪些权利？',
  '租赁合同到期后押金不退怎么办？',
  '行政处罚超过追责期限还能处罚吗？',
  '保证期间约定不明时如何计算？',
]

const desktopPromptPageSize = 6
const mobilePromptPageSize = 3

export function ConversationPanel(props: ConversationPanelProps) {
  const hasMessages = props.messages.length > 0
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const [promptPage, setPromptPage] = useState(0)
  const [mobilePrompts, setMobilePrompts] = useState(false)
  const currentQuery = () => textareaRef.current?.value ?? props.query
  const latestAssistant = [...props.messages].reverse().find((message) => message.role === 'assistant')
  const hasStreamingMessage = props.messages.some((message) => message.status === 'streaming')
  const submitLabel = '发送'
  const promptPageSize = mobilePrompts ? mobilePromptPageSize : desktopPromptPageSize
  const promptPageCount = Math.ceil(prompts.length / promptPageSize)
  const visiblePrompts = useMemo(() => {
    const start = (promptPage % promptPageCount) * promptPageSize
    return prompts.slice(start, start + promptPageSize)
  }, [promptPage, promptPageCount, promptPageSize])

  useEffect(() => {
    if (typeof window.matchMedia !== 'function') return undefined
    const media = window.matchMedia('(max-width: 760px)')
    const updatePromptLayout = () => setMobilePrompts(media.matches)
    updatePromptLayout()
    media.addEventListener('change', updatePromptLayout)
    return () => media.removeEventListener('change', updatePromptLayout)
  }, [])

  useEffect(() => {
    if (hasMessages || props.loading || promptPageCount <= 1) return undefined
    const timer = window.setInterval(() => {
      setPromptPage((current) => (current + 1) % promptPageCount)
    }, 9000)
    return () => window.clearInterval(timer)
  }, [hasMessages, props.loading, promptPageCount])

  return (
    <section className="conversation-panel" aria-label="法律咨询对话">
      <div className="panel-kicker">
        <span>CONVERSATION / 01</span>
        <b>{hasMessages ? '上下文对话' : '事实与问题'}</b>
      </div>
      <div className="conversation-scroll">
        {!hasMessages && !props.loading && (
          <div className="hero-copy" data-testid="prompt-stage">
            <div className="prompt-stage-head">
              <span>常见问题</span>
              <button
                type="button"
                data-testid="prompt-rotate"
                onClick={() => setPromptPage((current) => (current + 1) % promptPageCount)}
              >
                换一组问题
                <RotateCcw size={13} />
              </button>
            </div>
            <div className="prompt-grid">
              {visiblePrompts.map((prompt, index) => (
                <button
                  key={`${promptPage}-${prompt}`}
                  type="button"
                  data-testid="prompt-suggestion"
                  data-lawagent-prompt={prompt}
                  onClick={() => props.onSubmit(prompt)}
                >
                  <em>{String(promptPage * promptPageSize + index + 1).padStart(2, '0')}</em>
                  <span>{prompt}</span>
                  <ArrowUpRight size={15} />
                </button>
              ))}
            </div>
          </div>
        )}

        {hasMessages && (
          <div className="message-thread" data-lawagent-message-thread>
            {props.messages.map((message) => (
              <article className={`chat-bubble ${message.role}`} key={message.id}>
                <header>{message.role === 'user' ? '你' : 'LawAgent'}</header>
                <div className="bubble-content">
                  {message.role === 'assistant' && (message.structuredAnswer || message.content) ? (
                    <StructuredAnswerView
                      answer={message.structuredAnswer ?? fallbackStructuredAnswer(message.content)}
                      evidence={props.evidence}
                      onCitationSelect={props.onCitationSelect}
                    />
                  ) : (
                    message.content
                  )}
                  {message.status === 'streaming' && <span className="typing-cursor" aria-label="正在输出" />}
                </div>
              </article>
            ))}
            {props.loading && !hasStreamingMessage && (
              <article className="chat-bubble assistant pending">
                <header>LawAgent</header>
                <div className="bubble-content">
                  <LoaderCircle className="spin" size={15} />
                  正在检索法规、组织证据并审查风险…
                </div>
              </article>
            )}
          </div>
        )}

        {props.error && (
          <div className="error-card" role="alert">
            <b>暂时无法完成研究</b>
            <span>{props.error}</span>
            <button type="button" onClick={() => props.onSubmit(currentQuery())}>
              <RotateCcw size={14} />
              重新尝试
            </button>
          </div>
        )}
      </div>

      <div className="answer-actions" aria-label="回答操作">
        <button
          type="button"
          disabled={!latestAssistant?.content}
          onClick={() => copyText(latestAssistant?.content ?? '')}
        >
          <Clipboard size={14} />
          复制回答
        </button>
        <button
          type="button"
          disabled={!latestAssistant?.content}
          onClick={() => downloadMarkdown(latestAssistant?.content ?? '')}
        >
          <Download size={14} />
          导出 Markdown
        </button>
      </div>

      <div className="composer-shell">
        <textarea
          data-lawagent-query
          ref={textareaRef}
          value={props.query}
          onChange={(event) => props.onQueryChange(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter' && !event.shiftKey) {
              event.preventDefault()
              props.onSubmit(event.currentTarget.value)
            }
          }}
          placeholder={hasMessages ? '继续追问，或输入新的事实…' : '描述事实、时间与希望解决的问题…'}
          rows={3}
        />
        <div className="composer-meta">
          <span>
            <CornerDownLeft size={13} /> Enter 发送 · Shift + Enter 换行
          </span>
          <span>请勿输入身份证号等敏感信息</span>
        </div>
        <button
          className="submit-button"
          type="button"
          data-lawagent-submit
          disabled={props.loading}
          onClick={() => props.onSubmit(currentQuery())}
        >
          {submitLabel}
          {hasMessages ? <Send size={15} /> : <ArrowUpRight size={16} />}
        </button>
      </div>
    </section>
  )
}

function StructuredAnswerView({
  answer,
  evidence,
  onCitationSelect,
}: {
  answer: StructuredAnswer
  evidence: Evidence[]
  onCitationSelect: (id: string) => void
}) {
  const keyPoints = answer.key_points.filter((point) => !isStandaloneCitation(point))
  const citationIds = Array.from(new Set(answer.citations))
  return (
    <div className="structured-answer" data-lawagent-structured-answer>
      <section className="answer-section answer-summary">
        <h3><FileCheck2 size={16} />核心结论</h3>
        <p>
          <CitationText
            text={answer.summary}
            evidence={evidence}
            citations={citationIds}
            onCitationSelect={onCitationSelect}
          />
        </p>
      </section>
      {keyPoints.length > 0 && (
        <section className="answer-section">
          <h3><ListChecks size={16} />关键要点</h3>
          <ol>
            {keyPoints.map((point) => (
              <li key={point}>
                <span className="answer-point-text">
                  <CitationText
                    text={point}
                    evidence={evidence}
                    citations={citationIds}
                    onCitationSelect={onCitationSelect}
                  />
                </span>
              </li>
            ))}
          </ol>
        </section>
      )}
      {answer.analysis && (
        <section className="answer-section">
          <h3><Scale size={16} />分析过程</h3>
          <p>
            <CitationText
              text={answer.analysis}
              evidence={evidence}
              citations={citationIds}
              onCitationSelect={onCitationSelect}
            />
          </p>
        </section>
      )}
      {citationIds.length > 0 && (
        <section className="answer-sources" aria-label="引用依据">
          <span>引用依据</span>
          <div>
            {citationIds.map((citation) => (
              <button
                key={citation}
                type="button"
                title={citationTitle(citation, evidence, citationIds)}
                aria-label={`查看证据 ${citation}`}
                onClick={() => onCitationSelect(citation)}
              >
                <b>{citationLabel(citation, evidence, citationIds)}</b>
                <span>{citationSourceName(citation, evidence)}</span>
              </button>
            ))}
          </div>
        </section>
      )}
      {answer.notice && (
        <section className="answer-notice">
          <h3><ShieldAlert size={15} />适用提示</h3>
          <p>{answer.notice.replace(/^适用提示[：:]\s*/, '')}</p>
        </section>
      )}
    </div>
  )
}

function CitationText({
  text,
  evidence,
  citations,
  onCitationSelect,
}: {
  text: string
  evidence: Evidence[]
  citations: string[]
  onCitationSelect: (id: string) => void
}) {
  const parts = text.split(/(\[[a-zA-Z0-9_-]+\])/g)
  return (
    <>
      {parts.map((part, index) => {
        const match = /^\[([a-zA-Z0-9_-]+)\]$/.exec(part)
        if (!match) return <span key={`${part}-${index}`}>{part}</span>
        return (
          <button
            className="citation-chip"
            type="button"
            key={`${part}-${index}`}
            title={citationTitle(match[1], evidence, citations)}
            aria-label={`查看证据 ${match[1]}`}
            onClick={() => onCitationSelect(match[1])}
          >
            {citationLabel(match[1], evidence, citations)}
          </button>
        )
      })}
    </>
  )
}

function isStandaloneCitation(text: string) {
  return /^\s*\[?[A-Za-z0-9_-]{8,}\]?\s*$/.test(text)
}

function fallbackStructuredAnswer(content: string): StructuredAnswer {
  const mainText = content.split(/\n\n适用提示[：:]/)[0]?.trim() ?? content.trim()
  const paragraphs = mainText.split(/\n{2,}/).map((item) => item.trim()).filter(Boolean)
  const numberedPoints = Array.from(
    mainText.matchAll(/(?:^|\n)\s*\d+[.、]\s*(.+?)(?=\n\s*\d+[.、]|$)/gs),
    (match) => match[1].trim(),
  )
  const bulletPoints = Array.from(
    mainText.matchAll(/(?:^|\n)\s*[-•]\s+([^\n]+)/g),
    (match) => match[1].trim(),
  )
  const keyPoints = (numberedPoints.length ? numberedPoints : bulletPoints).filter(
    (point) => !isStandaloneCitation(point),
  )
  const prefix = mainText.split(/\n\s*(?:\d+[.、]|[-•])\s+/)[0]?.trim()
  const summary = prefix || paragraphs[0] || content
  const citations = Array.from(content.matchAll(/\[([A-Za-z0-9_-]+)\]/g), (match) => match[1])
    .filter((item, index, items) => items.indexOf(item) === index)
  return {
    summary,
    key_points: keyPoints,
    analysis: null,
    citations,
    notice: '',
  }
}

function citationLabel(citation: string, evidence: Evidence[], citations: string[]) {
  const index = citationIndex(citation, evidence, citations)
  return `证据 ${String(index).padStart(2, '0')}`
}

function citationSourceName(citation: string, evidence: Evidence[]) {
  const source = evidence.find((item) => item.article_id === citation)
  if (!source) return '法规证据'
  return `${source.law_name} ${source.article_number}`.trim()
}

function citationTitle(citation: string, evidence: Evidence[], citations: string[]) {
  return `${citationLabel(citation, evidence, citations)} · ${citationSourceName(citation, evidence)} · ${citation}`
}

function citationIndex(citation: string, evidence: Evidence[], citations: string[]) {
  const evidenceIndex = evidence.findIndex((item) => item.article_id === citation)
  if (evidenceIndex >= 0) return evidenceIndex + 1
  const citationIndexValue = citations.indexOf(citation)
  if (citationIndexValue >= 0) return citationIndexValue + 1
  return 1
}

function copyText(text: string) {
  void navigator.clipboard?.writeText(text)
}

function downloadMarkdown(text: string) {
  const blob = new Blob([`# LawAgent 回答\n\n${text}\n`], { type: 'text/markdown;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = 'lawagent-answer.md'
  anchor.click()
  URL.revokeObjectURL(url)
}
