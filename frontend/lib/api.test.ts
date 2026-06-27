import { describe, expect, it, vi } from 'vitest'

import {
  createChatRun,
  getAdminOverview,
  getSession,
  listSessions,
  initialRunState,
  reduceAgentEvent,
  streamChatRun,
} from './api'

describe('reduceAgentEvent', () => {
  it('applies ordered workflow events to the trace', () => {
    const started = reduceAgentEvent(initialRunState, {
      sequence: 1,
      type: 'agent.started',
      agent: 'legal_research',
      summary: '开始检索',
    })
    const completed = reduceAgentEvent(started, {
      sequence: 2,
      type: 'agent.completed',
      agent: 'legal_research',
      summary: '检索完成',
    })

    expect(completed.lastSequence).toBe(2)
    expect(completed.events).toHaveLength(2)
    expect(completed.activeAgent).toBeNull()
  })

  it('ignores replayed or out-of-order events', () => {
    const state = { ...initialRunState, lastSequence: 3 }
    const result = reduceAgentEvent(state, {
      sequence: 2,
      type: 'agent.started',
      agent: 'critic',
      summary: '重复事件',
    })

    expect(result).toBe(state)
  })
})

describe('chat API helpers', () => {
  it('passes the active session id when creating a chat run', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ run_id: 'run-1', session_id: 'session-1', events_url: '', result: {} }),
    })
    vi.stubGlobal('fetch', fetchMock)

    await createChatRun('那保证期间呢？', 'session-1')

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/chat',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ message: '那保证期间呢？', session_id: 'session-1' }),
      }),
    )
  })

  it('loads session summaries and messages for history management', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        json: async () => [
          {
            id: 'session-1',
            title: '民法典保证责任有哪些规定？',
            last_message: '保证责任包括一般保证和连带责任保证。',
            created_at: '2026-06-21 10:00:00',
            updated_at: '2026-06-21 10:01:00',
            message_count: 2,
            run_count: 1,
          },
        ],
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => [
          { role: 'user', content: '民法典保证责任有哪些规定？', created_at: '2026-06-21' },
          { role: 'assistant', content: '保证责任包括一般保证和连带责任保证。', created_at: '2026-06-21' },
        ],
      })
    vi.stubGlobal('fetch', fetchMock)

    await expect(listSessions()).resolves.toHaveLength(1)
    await expect(getSession('session-1')).resolves.toHaveLength(2)
    expect(fetchMock).toHaveBeenNthCalledWith(1, '/api/v1/sessions')
    expect(fetchMock).toHaveBeenNthCalledWith(2, '/api/v1/sessions/session-1')
  })

  it('loads admin overview with the admin access token', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        corpus: { status: 'available', report_url: '/data/reports/corpus.json' },
        index: { status: 'available', metadata: { article_count: 45552, dimension: 1024 } },
        recent_runs: [],
        evaluation: { open_ended_case_count: 10, categories: ['multi_statute_synthesis'] },
      }),
    })
    vi.stubGlobal('fetch', fetchMock)

    await expect(getAdminOverview('admin-test')).resolves.toMatchObject({
      evaluation: { open_ended_case_count: 10 },
    })
    expect(fetchMock).toHaveBeenCalledWith('/api/v1/admin/overview', {
      headers: { 'x-admin-key': 'admin-test' },
    })
  })

  it('parses split SSE frames and streams answer deltas before completion', async () => {
    const encoder = new TextEncoder()
    const chunks = [
      'event: session.started\ndata: {"session_id":"session-1"}\n\nevent: answer.',
      'delta\ndata: {"delta":"第一段"}\n\nevent: answer.delta\ndata: {"delta":"第二段"}\n\n',
      'event: chat.completed\ndata: {"run_id":"run-1","session_id":"session-1","events_url":"/events","result":{"status":"completed","route":"simple","risk_level":"low","answer":"第一段第二段","clarification":null,"evidence":[],"analysis":null,"agents_executed":[],"retry_count":0,"tool_calls":0,"events":[],"structured_answer":null}}\n\n',
    ]
    let index = 0
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      body: {
        getReader: () => ({
          read: async () =>
            index < chunks.length
              ? { done: false, value: encoder.encode(chunks[index++]) }
              : { done: true, value: undefined },
        }),
      },
    })
    vi.stubGlobal('fetch', fetchMock)
    const deltas: string[] = []

    const result = await streamChatRun('测试问题', undefined, {
      onAnswerDelta: (delta) => deltas.push(delta),
    })

    expect(deltas).toEqual(['第一段', '第二段'])
    expect(result.run_id).toBe('run-1')
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/chat/stream',
      expect.objectContaining({ method: 'POST' }),
    )
  })
})
