import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { createChatRun, subscribeToRun } from '../lib/api'
import type { ChatRun } from '../lib/types'
import { LegalWorkspace } from './LegalWorkspace'

vi.mock('../lib/api', async () => {
  const actual = await vi.importActual<typeof import('../lib/api')>('../lib/api')
  return {
    ...actual,
    createChatRun: vi.fn(),
    subscribeToRun: vi.fn(() => vi.fn()),
  }
})

const mockedCreateChatRun = vi.mocked(createChatRun)
const mockedSubscribeToRun = vi.mocked(subscribeToRun)

afterEach(cleanup)

const run: ChatRun = {
  run_id: 'run-1',
  session_id: 'session-1',
  events_url: '/api/v1/chat/run-1/events',
  result: {
    status: 'completed' as const,
    route: 'complex' as const,
    risk_level: 'medium' as const,
    answer: '根据劳动合同法，经济补偿通常按工作年限计算。',
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
  },
}

describe('LegalWorkspace', () => {
  beforeEach(() => {
    mockedCreateChatRun.mockReset()
    mockedSubscribeToRun.mockClear()
  })

  it('submits a question and renders answer, evidence, and trace', async () => {
    mockedCreateChatRun.mockResolvedValue(run)
    render(<LegalWorkspace />)

    fireEvent.change(screen.getByPlaceholderText('描述事实、时间与希望解决的问题…'), {
      target: { value: '公司违法辞退我，经济补偿如何计算？' },
    })
    fireEvent.click(screen.getByRole('button', { name: '开始研究' }))

    await screen.findByText(/经济补偿通常按工作年限计算/)
    expect(screen.getByText('中华人民共和国劳动合同法')).toBeInTheDocument()
    expect(screen.getByText('法律研究员')).toBeInTheDocument()
    expect(mockedSubscribeToRun).toHaveBeenCalledWith(
      '/api/v1/chat/run-1/events',
      expect.any(Function),
      expect.any(Function),
    )
  })

  it('supports keyboard submission and exposes mobile panel tabs', async () => {
    mockedCreateChatRun.mockResolvedValue(run)
    render(<LegalWorkspace />)
    const input = screen.getByPlaceholderText('描述事实、时间与希望解决的问题…')

    fireEvent.change(input, { target: { value: '劳动合同法第四十七条是什么？' } })
    fireEvent.keyDown(input, { key: 'Enter', ctrlKey: true })

    await screen.findByText(/经济补偿通常按工作年限计算/)
    fireEvent.click(screen.getByRole('tab', { name: '证据' }))
    expect(screen.getByRole('tab', { name: '证据' })).toHaveAttribute('aria-selected', 'true')
  })

  it('shows a recoverable error when the API fails', async () => {
    mockedCreateChatRun.mockRejectedValue(new Error('network failed'))
    render(<LegalWorkspace />)

    fireEvent.change(screen.getByPlaceholderText('描述事实、时间与希望解决的问题…'), {
      target: { value: '劳动合同解除有什么规定？' },
    })
    fireEvent.click(screen.getByRole('button', { name: '开始研究' }))

    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('暂时无法完成研究'))
    expect(screen.getByRole('button', { name: '重新尝试' })).toBeInTheDocument()
  })
})
