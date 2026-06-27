import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { getAdminOverview } from '../lib/api'
import { AdminDashboard } from './AdminDashboard'

vi.mock('../lib/api', async () => {
  const actual = await vi.importActual<typeof import('../lib/api')>('../lib/api')
  return {
    ...actual,
    getAdminOverview: vi.fn(),
  }
})

const mockedGetAdminOverview = vi.mocked(getAdminOverview)

afterEach(cleanup)

describe('AdminDashboard', () => {
  beforeEach(() => {
    mockedGetAdminOverview.mockReset()
  })

  it('loads corpus, index, recent run, and open-ended evaluation status', async () => {
    mockedGetAdminOverview.mockResolvedValue({
      corpus: {
        status: 'available',
        report_url: '/data/reports/corpus.json',
        report: { total_files: 1000, accepted: 998, article_count: 45552 },
      },
      index: {
        status: 'available',
        metadata: { embedding_model: 'text-embedding-v4', article_count: 45552, dimension: 1024 },
      },
      recent_runs: [
        {
          id: 'run-1',
          query: '民法典保证责任有哪些规定？',
          status: 'completed',
          route: 'simple',
          risk_level: 'low',
          created_at: '2026-06-21',
          agents_executed: ['supervisor', 'legal_research'],
          evidence_count: 8,
        },
      ],
      evaluation: {
        open_ended_case_count: 10,
        categories: ['multi_statute_synthesis', 'version_difference'],
      },
    })

    render(<AdminDashboard />)
    fireEvent.change(screen.getByLabelText('Admin Token'), { target: { value: 'admin-test' } })
    fireEvent.click(screen.getByRole('button', { name: '加载后台状态' }))

    await screen.findByText('45,552')
    expect(screen.getByText('10')).toBeInTheDocument()
    expect(screen.getByText('民法典保证责任有哪些规定？')).toBeInTheDocument()
  })
})
