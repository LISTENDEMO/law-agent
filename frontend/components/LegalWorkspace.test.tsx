import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { deleteSession, getLatestSessionRun, getSession, listSessions, streamChatRun } from '../lib/api'
import type { ChatRun } from '../lib/types'
import { LegalWorkspace } from './LegalWorkspace'

vi.mock('../lib/api', async () => {
  const actual = await vi.importActual<typeof import('../lib/api')>('../lib/api')
  return {
    ...actual,
    getSession: vi.fn(),
    getLatestSessionRun: vi.fn(),
    listSessions: vi.fn(),
    deleteSession: vi.fn(),
    streamChatRun: vi.fn(),
  }
})

const mockedDeleteSession = vi.mocked(deleteSession)
const mockedGetLatestSessionRun = vi.mocked(getLatestSessionRun)
const mockedGetSession = vi.mocked(getSession)
const mockedListSessions = vi.mocked(listSessions)
const mockedStreamChatRun = vi.mocked(streamChatRun)

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

const run: ChatRun = {
  run_id: 'run-1',
  session_id: 'session-1',
  events_url: '/api/v1/chat/run-1/events',
  result: {
    status: 'completed' as const,
    route: 'complex' as const,
    risk_level: 'medium' as const,
    answer: '根据劳动合同法，经济补偿通常按工作年限计算。[labor-47]\n\n如果涉及保证责任，还应核对民法典保证方式。[civil-686]',
    clarification: null,
    evidence: [
      {
        article_id: 'labor-47',
        law_name: '中华人民共和国劳动合同法',
        article_number: '第四十七条',
        content: '经济补偿按劳动者在本单位工作的年限计算。',
        score: 0.92,
        retrieval_mode: 'hybrid',
        source_date: '2012-12-28',
        status: 'effective',
      },
      {
        article_id: 'civil-686',
        law_name: '中华人民共和国民法典',
        article_number: '第六百八十六条',
        content: '保证的方式包括一般保证和连带责任保证。',
        score: 0.88,
        retrieval_mode: 'hybrid',
        source_date: '2020-05-28',
        status: 'effective',
      },
    ],
    analysis: '已完成法律要件映射。',
    agents_executed: ['supervisor', 'legal_research', 'legal_analysis'],
    retry_count: 0,
    tool_calls: 1,
    events: [
      { sequence: 1, type: 'run.started', agent: 'supervisor', summary: '开始评估问题' },
      {
        sequence: 2,
        type: 'agent.completed',
        agent: 'legal_research',
        summary: '检索完成',
      },
      { sequence: 3, type: 'run.completed', agent: null, summary: '工作流完成' },
    ],
    structured_answer: {
      summary: '违法解除时，赔偿通常与工作年限相关。',
      key_points: ['先确认解除是否合法。', '再根据工作年限计算补偿或赔偿。'],
      analysis: '已完成法律要件映射。',
      citations: ['labor-47', 'civil-686'],
      notice: '适用提示：本回答不构成正式法律意见。',
    },
    retrieval_metrics: {
      k: 8,
      retrieved_count: 2,
      recall_at_k: null,
      status: 'pending_gold',
    },
  },
}

describe('LegalWorkspace', () => {
  beforeEach(() => {
    mockedGetSession.mockReset()
    mockedGetLatestSessionRun.mockReset()
    mockedGetLatestSessionRun.mockResolvedValue(null)
    mockedListSessions.mockReset()
    mockedListSessions.mockResolvedValue([])
    mockedDeleteSession.mockReset()
    mockedDeleteSession.mockResolvedValue()
    mockedStreamChatRun.mockReset()
    mockedStreamChatRun.mockImplementation(async (_message, _sessionId, handlers) => {
      handlers.onSession?.(run.session_id)
      run.result.events.forEach((event) => handlers.onAgentEvent?.(event))
      handlers.onAnswerDelta?.(run.result.answer)
      return run
    })
  })

  it('submits a question and renders answer, evidence, and trace', async () => {
    render(<LegalWorkspace />)

    fireEvent.change(screen.getByPlaceholderText('描述事实、时间与希望解决的问题…'), {
      target: { value: '公司违法辞退我，经济补偿如何计算？' },
    })
    fireEvent.click(screen.getByRole('button', { name: '发送' }))

    await screen.findByText(/经济补偿通常按工作年限计算/)
    expect(screen.getByText('中华人民共和国劳动合同法')).toBeInTheDocument()
    expect(screen.getByText('Recall@8')).toBeInTheDocument()
    expect(screen.getByText('待评测')).toBeInTheDocument()
    expect(screen.getByText('法律研究员')).toBeInTheDocument()
    expect(mockedStreamChatRun).toHaveBeenCalledWith(
      '公司违法辞退我，经济补偿如何计算？',
      undefined,
      expect.any(Object),
    )
  })

  it('supports keyboard submission and exposes mobile panel tabs', async () => {
    render(<LegalWorkspace />)
    const input = screen.getByPlaceholderText('描述事实、时间与希望解决的问题…')

    fireEvent.change(input, { target: { value: '劳动合同法第四十七条是什么？' } })
    fireEvent.keyDown(input, { key: 'Enter' })

    await screen.findByText(/经济补偿通常按工作年限计算/)
    fireEvent.click(screen.getByRole('tab', { name: '证据' }))
    expect(screen.getByRole('tab', { name: '证据' })).toHaveAttribute('aria-selected', 'true')
  })

  it('shows a recoverable error when the API fails', async () => {
    mockedStreamChatRun.mockRejectedValue(new Error('network failed'))
    render(<LegalWorkspace />)

    fireEvent.change(screen.getByPlaceholderText('描述事实、时间与希望解决的问题…'), {
      target: { value: '劳动合同解除有什么规定？' },
    })
    fireEvent.click(screen.getByRole('button', { name: '发送' }))

    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('暂时无法完成研究'))
    expect(screen.getByRole('button', { name: '重新尝试' })).toBeInTheDocument()
  })

  it('submits the current textarea value even when React change state is stale', async () => {
    render(<LegalWorkspace />)
    const input = screen.getByPlaceholderText('描述事实、时间与希望解决的问题…')
    const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value')?.set

    setter?.call(input, '民法典关于保证责任有哪些规定？')
    fireEvent.click(screen.getByRole('button', { name: '发送' }))

    await waitFor(() =>
      expect(mockedStreamChatRun).toHaveBeenCalledWith(
        '民法典关于保证责任有哪些规定？',
        undefined,
        expect.any(Object),
      ),
    )
  })

  it('exposes stable fallback hooks for non-hydrated browser interaction', () => {
    render(<LegalWorkspace />)

    expect(screen.getByPlaceholderText('描述事实、时间与希望解决的问题…')).toHaveAttribute(
      'data-lawagent-query',
    )
    expect(screen.getByRole('button', { name: '发送' })).toHaveAttribute(
      'data-lawagent-submit',
    )
    expect(screen.getByRole('button', { name: /民法典关于保证责任/ })).toHaveAttribute(
      'data-lawagent-prompt',
    )
  })

  it('centers a larger rotating prompt pool on new conversations', () => {
    render(<LegalWorkspace />)

    const firstGroup = screen.getAllByTestId('prompt-suggestion')
    expect(firstGroup).toHaveLength(6)
    expect(screen.getByTestId('prompt-stage')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: '换一组问题' }))

    const secondGroup = screen.getAllByTestId('prompt-suggestion')
    expect(secondGroup).toHaveLength(6)
    expect(secondGroup.map((item) => item.textContent).join('')).not.toBe(
      firstGroup.map((item) => item.textContent).join(''),
    )
  })

  it('shows three rotating prompt suggestions on mobile', async () => {
    vi.stubGlobal('matchMedia', vi.fn().mockReturnValue({
      matches: true,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    }))

    render(<LegalWorkspace />)

    await waitFor(() => expect(screen.getAllByTestId('prompt-suggestion')).toHaveLength(3))

    const firstGroup = screen.getAllByTestId('prompt-suggestion')
    fireEvent.click(screen.getByRole('button', { name: '换一组问题' }))
    const secondGroup = screen.getAllByTestId('prompt-suggestion')

    expect(secondGroup).toHaveLength(3)
    expect(secondGroup.map((item) => item.textContent).join('')).not.toBe(
      firstGroup.map((item) => item.textContent).join(''),
    )
  })

  it('submits a prompt suggestion immediately when clicked', async () => {
    render(<LegalWorkspace />)

    fireEvent.click(screen.getByRole('button', { name: /借款到期后诉讼时效怎么计算/ }))

    await waitFor(() =>
      expect(mockedStreamChatRun).toHaveBeenCalledWith(
        '借款到期后诉讼时效怎么计算？',
        undefined,
        expect.any(Object),
      ),
    )
  })

  it('loads history sessions and reuses selected session context', async () => {
    mockedListSessions.mockResolvedValue([
      {
        id: 'session-1',
        title: '民法典保证责任有哪些规定？',
        last_message: '保证责任包括一般保证和连带责任保证。',
        created_at: '2026-06-21 10:00:00',
        updated_at: '2026-06-21 10:01:00',
        message_count: 2,
        run_count: 1,
      },
    ])
    mockedGetSession.mockResolvedValue([
      { role: 'user', content: '民法典保证责任有哪些规定？', created_at: '2026-06-21' },
      {
        role: 'assistant',
        content: '保证责任包括一般保证和连带责任保证。',
        created_at: '2026-06-21',
        structured_answer: run.result.structured_answer,
      },
    ])
    mockedGetLatestSessionRun.mockResolvedValue(run)
    render(<LegalWorkspace />)

    fireEvent.click(await screen.findByRole('button', { name: /^民法典保证责任有哪些规定？$/ }))
    await screen.findByText('核心结论')
    expect(await screen.findByText('中华人民共和国劳动合同法')).toBeInTheDocument()
    expect(screen.getByText('法律研究员')).toBeInTheDocument()
    fireEvent.change(screen.getByPlaceholderText('继续追问，或输入新的事实…'), {
      target: { value: '那保证期间呢？' },
    })
    fireEvent.click(screen.getByRole('button', { name: '发送' }))

    await waitFor(() =>
      expect(mockedStreamChatRun).toHaveBeenCalledWith(
        '那保证期间呢？',
        'session-1',
        expect.any(Object),
      ),
    )
  })

  it('opens a mobile history drawer and closes it after selecting a session', async () => {
    mockedListSessions.mockResolvedValue([
      {
        id: 'session-1',
        title: '民法典保证责任有哪些规定？',
        last_message: '保证责任包括一般保证和连带责任保证。',
        created_at: '2026-06-21 10:00:00',
        updated_at: '2026-06-21 10:01:00',
        message_count: 2,
        run_count: 1,
      },
    ])
    mockedGetSession.mockResolvedValue([
      { role: 'user', content: '民法典保证责任有哪些规定？', created_at: '2026-06-21' },
      {
        role: 'assistant',
        content: '保证责任包括一般保证和连带责任保证。',
        created_at: '2026-06-21',
        structured_answer: run.result.structured_answer,
      },
    ])
    mockedGetLatestSessionRun.mockResolvedValue(run)

    render(<LegalWorkspace />)

    fireEvent.click(screen.getByRole('button', { name: '打开历史会话' }))
    const drawer = screen.getByTestId('mobile-history-drawer')
    expect(drawer).toHaveAttribute('data-open', 'true')

    fireEvent.click(await screen.findByRole('button', { name: /^民法典保证责任有哪些规定？$/ }))

    await screen.findByText('核心结论')
    expect(drawer).toHaveAttribute('data-open', 'false')
  })

  it('deletes a history session without opening it', async () => {
    mockedListSessions.mockResolvedValue([
      {
        id: 'session-1',
        title: '民法典保证责任有哪些规定？',
        last_message: '保证责任包括一般保证和连带责任保证。',
        created_at: '2026-06-21 10:00:00',
        updated_at: '2026-06-21 10:01:00',
        message_count: 2,
        run_count: 1,
      },
    ])
    render(<LegalWorkspace />)

    fireEvent.click(await screen.findByRole('button', { name: /删除会话 民法典保证责任有哪些规定/ }))

    await waitFor(() => expect(mockedDeleteSession).toHaveBeenCalledWith('session-1'))
    expect(mockedGetSession).not.toHaveBeenCalled()
  })

  it('turns answer citation ids into evidence selection controls', async () => {
    render(<LegalWorkspace />)

    fireEvent.change(screen.getByPlaceholderText('描述事实、时间与希望解决的问题…'), {
      target: { value: '公司违法辞退我，经济补偿如何计算？' },
    })
    fireEvent.click(screen.getByRole('button', { name: '发送' }))

    await screen.findByText('核心结论')
    fireEvent.click(screen.getByRole('button', { name: /查看证据 civil-686/ }))
    await waitFor(() => expect(screen.getByTestId('evidence-card-civil-686')).toHaveClass('active'))
  })

  it('renders long citation ids as compact controls instead of raw inline hashes', async () => {
    const longCitationRun: ChatRun = {
      ...run,
      result: {
        ...run.result,
        evidence: [
          {
            article_id: '822dd54d44335ef318746ffa',
            law_name: '中华人民共和国民法典',
            article_number: '第一百八十八条',
            content: '向人民法院请求保护民事权利的诉讼时效期间为三年。',
            score: 0.93,
            retrieval_mode: 'hybrid',
            source_date: '2020-05-28',
            status: 'effective',
          },
        ],
        structured_answer: {
          ...run.result.structured_answer!,
          summary: '结论需要核对。[822dd54d44335ef318746ffa]',
          key_points: [
            '现行规则为三年。[822dd54d44335ef318746ffa]',
            '[822dd54d44335ef318746ffa]',
          ],
          citations: ['822dd54d44335ef318746ffa'],
        },
      },
    }
    mockedStreamChatRun.mockImplementation(async (_message, _sessionId, handlers) => {
      handlers.onAnswerDelta?.(longCitationRun.result.answer)
      return longCitationRun
    })
    render(<LegalWorkspace />)

    fireEvent.change(screen.getByPlaceholderText('描述事实、时间与希望解决的问题…'), {
      target: { value: '诉讼时效怎么计算？' },
    })
    fireEvent.click(screen.getByRole('button', { name: '发送' }))

    const [citation] = await screen.findAllByRole('button', {
      name: /查看证据 822dd54d44335ef318746ffa/,
    })
    expect(citation).toHaveTextContent('证据 01')
    expect(screen.getByText(/中华人民共和国民法典 第一百八十八条/)).toBeInTheDocument()
    expect(
      screen
        .getAllByRole('listitem')
        .some((item) => item.textContent?.trim() === '证据 01'),
    ).toBe(false)
    const point = screen.getByText(/现行规则为三年/).closest('.answer-point-text')
    expect(point).not.toBeNull()
    expect(point).toHaveTextContent('证据 01')
  })

  it('clears the composer immediately and renders answer deltas before completion', async () => {
    let finish: ((value: ChatRun) => void) | undefined
    mockedStreamChatRun.mockImplementation(async (_message, _sessionId, handlers) => {
      handlers.onSession?.('session-1')
      handlers.onAgentEvent?.(run.result.events[0])
      handlers.onAnswerDelta?.('正在流式生成第一段')
      return await new Promise<ChatRun>((resolve) => {
        finish = resolve
      })
    })
    render(<LegalWorkspace />)
    const input = screen.getByPlaceholderText('描述事实、时间与希望解决的问题…')

    fireEvent.change(input, { target: { value: '公司违法辞退我怎么办？' } })
    fireEvent.click(screen.getByRole('button', { name: '发送' }))

    expect(input).toHaveValue('')
    expect(await screen.findByText('核心结论')).toBeInTheDocument()
    expect(screen.getByText('正在流式生成第一段')).toBeInTheDocument()
    finish?.(run)
    await screen.findByText('核心结论')
  })

  it('renders the completed answer as structured legal sections', async () => {
    mockedStreamChatRun.mockImplementation(async (_message, _sessionId, handlers) => {
      handlers.onAnswerDelta?.(run.result.answer)
      return run
    })
    render(<LegalWorkspace />)

    fireEvent.change(screen.getByPlaceholderText('描述事实、时间与希望解决的问题…'), {
      target: { value: '公司违法辞退我，经济补偿如何计算？' },
    })
    fireEvent.click(screen.getByRole('button', { name: '发送' }))

    expect(await screen.findByText('核心结论')).toBeInTheDocument()
    expect(screen.getByText('关键要点')).toBeInTheDocument()
    expect(screen.getByText('分析过程')).toBeInTheDocument()
    expect(screen.getByText('适用提示')).toBeInTheDocument()
  })
})
