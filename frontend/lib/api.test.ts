import { describe, expect, it } from 'vitest'

import { initialRunState, reduceAgentEvent } from './api'

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
