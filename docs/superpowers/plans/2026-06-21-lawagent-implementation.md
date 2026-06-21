# LawAgent Full-System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a runnable, attractive, evaluated multi-agent legal research application over the existing 1032-document corpus.

**Architecture:** A Next.js frontend consumes a FastAPI backend over JSON and SSE. The backend is a modular monolith containing corpus ingestion, hybrid retrieval, a controlled supervisor/specialist workflow, citation verification, tracing, and evaluation. SQLite, a local BM25 index, and a local vector index provide reproducible persistence without premature distributed infrastructure.

**Tech Stack:** Python 3.11+, FastAPI, Pydantic, OpenAI-compatible SDK, python-docx, rank-bm25, NumPy, SQLite, Next.js, React, TypeScript, Tailwind CSS, Vitest, Playwright, Pytest, Docker Compose.

---

## File map

```text
backend/
├── app/main.py                 # FastAPI composition and lifecycle
├── app/config.py               # Environment-backed settings
├── app/api/chat.py             # Chat, session, source, and SSE routes
├── app/api/admin.py            # Corpus and evaluation administration
├── app/domain/models.py        # Shared Pydantic contracts
├── app/corpus/parser.py        # DOCX legal hierarchy parser
├── app/corpus/ingest.py        # Deduplication and quality report
├── app/rag/index.py            # Persistent BM25/vector document index
├── app/rag/retriever.py        # Hybrid search, RRF, and rerank contract
├── app/agents/model_client.py   # OpenAI-compatible chat/embedding adapters
├── app/agents/workflow.py       # Supervisor and specialist orchestration
├── app/verification/citations.py# Deterministic citation validation
├── app/storage/repository.py    # SQLite sessions, traces, and sources
├── app/evaluation/runner.py     # Dataset metrics and comparisons
└── tests/                       # Unit and API tests

frontend/
├── app/page.tsx                 # Main legal research workspace
├── app/layout.tsx               # Fonts, metadata, application shell
├── app/globals.css              # Editorial legal design system
├── components/                  # Chat, evidence, trace, and navigation
├── lib/api.ts                   # Typed API and SSE client
├── lib/types.ts                 # Shared frontend contracts
└── tests/                       # Component and unit tests

data/
├── normalized/                  # Generated normalized legal JSONL
├── indexes/                     # Generated BM25/vector artifacts
├── reports/                     # Corpus and evaluation reports
└── lawagent.db                  # Generated SQLite database
```

## Task 1: Project foundation and secure configuration

**Files:**
- Create: `.gitignore`, `.env`, `.env.example`, `pyproject.toml`
- Create: `backend/app/__init__.py`, `backend/app/config.py`
- Test: `backend/tests/test_config.py`

- [ ] Write a config test proving chat and embedding providers load from environment while secret values never appear in `repr`.
- [ ] Run `pytest backend/tests/test_config.py -v` and confirm failure because the settings module is absent.
- [ ] Implement typed settings for chat base URL, chat key/model, embedding base URL, embedding key/model, paths, limits, and offline-test mode.
- [ ] Add real credentials only to ignored `.env`; add placeholders to `.env.example`.
- [ ] Run the config test and secret-scan commands; confirm no key pattern exists outside `.env`.

## Task 2: Domain contracts and legal document parser

**Files:**
- Create: `backend/app/domain/models.py`
- Create: `backend/app/corpus/parser.py`
- Test: `backend/tests/corpus/test_parser.py`

- [ ] Write failing tests for Chinese article headings, paragraphs, metadata inferred from filenames, stable IDs, empty documents, and a representative DOCX fixture.
- [ ] Run parser tests and confirm missing imports/functions cause the expected failures.
- [ ] Implement `LawDocument`, `LegalArticle`, `Evidence`, `CorpusIssue`, and `CorpusReport` contracts.
- [ ] Implement paragraph extraction and article-aware splitting with a fallback chunker only when no article structure exists.
- [ ] Run parser tests and confirm all cases pass.

## Task 3: Corpus ingestion, deduplication, and reporting

**Files:**
- Create: `backend/app/corpus/ingest.py`
- Create: `backend/app/cli.py`
- Test: `backend/tests/corpus/test_ingest.py`

- [ ] Write failing tests for exact duplicate hashes, normalized-text duplicates, unsupported DOC quarantine, and incremental unchanged documents.
- [ ] Verify tests fail for missing ingestion behavior.
- [ ] Implement deterministic SHA-256 deduplication, processing statuses, JSONL output, and a machine-readable quality report.
- [ ] Add `python -m app.cli ingest` with input/output options and progress reporting that never exposes document contents.
- [ ] Run ingestion tests, then ingest a small representative subset and inspect the generated report.

## Task 4: Hybrid index and retrieval

**Files:**
- Create: `backend/app/rag/index.py`
- Create: `backend/app/rag/retriever.py`
- Test: `backend/tests/rag/test_retriever.py`

- [ ] Write failing tests for BM25 exact-term retrieval, vector semantic ranking, metadata filtering, deterministic RRF ordering, deduplication, and embedding failure fallback.
- [ ] Verify retrieval tests fail because no index exists.
- [ ] Implement persistent article metadata, BM25 indexing, batched embedding generation, cosine similarity, RRF fusion, and a pluggable reranker interface.
- [ ] Ensure effective-date and jurisdiction filters run before final evidence selection.
- [ ] Run retrieval tests and build a small local index using deterministic test embeddings.

## Task 5: Model adapters and deterministic citation verifier

**Files:**
- Create: `backend/app/agents/model_client.py`
- Create: `backend/app/verification/citations.py`
- Test: `backend/tests/agents/test_model_client.py`
- Test: `backend/tests/verification/test_citations.py`

- [ ] Write failing tests for OpenAI-compatible request construction, timeout mapping, structured JSON parsing, batch embeddings, unknown citation IDs, quote mismatch, and unsupported claims.
- [ ] Verify all tests fail for the intended missing behavior.
- [ ] Implement dependency-injected chat and embedding clients with bounded retries and redacted exceptions.
- [ ] Implement exact article-ID, normalized quote, effective-date, and claim-evidence coverage checks.
- [ ] Run model and citation tests with fake transports; make no paid/network call in unit tests.

## Task 6: Controlled multi-agent workflow

**Files:**
- Create: `backend/app/agents/prompts.py`
- Create: `backend/app/agents/workflow.py`
- Test: `backend/tests/agents/test_workflow.py`

- [ ] Write failing tests proving the supervisor requests clarification, delegates simple research, delegates complex research plus analysis, invokes critic for high risk, retries insufficient evidence at most twice, and terminates on budget exhaustion.
- [ ] Verify tests fail for missing workflow.
- [ ] Implement structured supervisor decisions and Research, Analysis, and Critic specialist contracts with separate tool permissions.
- [ ] Implement bounded orchestration, event emission, deterministic citation verification, graceful failure, and an offline deterministic mode for repeatable tests/demo fallback.
- [ ] Run workflow tests and confirm no path can loop without decrementing a budget.

## Task 7: Persistence, FastAPI, and SSE

**Files:**
- Create: `backend/app/storage/repository.py`
- Create: `backend/app/api/chat.py`, `backend/app/api/admin.py`
- Create: `backend/app/main.py`
- Test: `backend/tests/api/test_chat.py`, `backend/tests/storage/test_repository.py`

- [ ] Write failing tests for session creation, chat run creation, ordered events, source lookup, session deletion, admin authentication, rate limiting, and health/readiness separation.
- [ ] Verify API tests fail before route implementation.
- [ ] Implement SQLite migrations and repositories with short transactions and JSON validation.
- [ ] Implement `/api/v1/chat`, SSE event replay, sessions, sources, health, corpus report, index build, and evaluation endpoints.
- [ ] Run API tests and inspect OpenAPI generation.

## Task 8: Evaluation dataset and metrics

**Files:**
- Create: `backend/app/evaluation/runner.py`
- Create: `backend/data/evaluation/dev.jsonl`, `backend/data/evaluation/gold.sample.jsonl`
- Test: `backend/tests/evaluation/test_runner.py`

- [ ] Write failing tests for Recall@K, MRR, citation precision/completeness, route accuracy, aggregate latency, and zero-result behavior.
- [ ] Verify expected failures.
- [ ] Implement deterministic metric functions, dataset validation, per-example output, aggregate reports, and experiment labels.
- [ ] Seed representative evaluation cases from the available corpus without fabricating authoritative answers.
- [ ] Run evaluation unit tests and a small offline baseline.

## Task 9: Distinctive frontend foundation

**Files:**
- Create: `frontend/package.json`, `frontend/tsconfig.json`, `frontend/next.config.mjs`
- Create: `frontend/app/layout.tsx`, `frontend/app/globals.css`, `frontend/app/page.tsx`
- Create: `frontend/lib/types.ts`, `frontend/lib/api.ts`
- Test: `frontend/lib/api.test.ts`

- [ ] Define the visual direction: refined Chinese legal editorial workspace, ink-black/navy surfaces, parchment highlights, vermilion status accents, high-contrast serif headings, restrained motion, and dense-but-calm evidence presentation.
- [ ] Write failing client tests for chat creation, SSE event reduction, reconnection sequence handling, and API errors.
- [ ] Verify frontend tests fail before implementation.
- [ ] Implement strict typed contracts and API/SSE client.
- [ ] Implement responsive application shell, atmospheric background, accessible focus states, reduced-motion support, and route error boundary.
- [ ] Run unit tests, TypeScript, and lint.

## Task 10: Interactive chat, sources, and trace UI

**Files:**
- Create: `frontend/components/LegalWorkspace.tsx`
- Create: `frontend/components/ConversationPanel.tsx`
- Create: `frontend/components/EvidencePanel.tsx`
- Create: `frontend/components/TraceRail.tsx`
- Create: `frontend/components/StatusHeader.tsx`
- Test: `frontend/components/LegalWorkspace.test.tsx`

- [ ] Write failing component tests for message submission, streaming deltas, clarification mode, evidence selection, trace progression, failures, keyboard submission, and mobile tabs.
- [ ] Verify component tests fail for missing components.
- [ ] Implement the workspace with real API state, rich empty state prompts, progressive answer rendering, source cards, agent timeline, copy feedback, and responsive panels.
- [ ] Add purposeful entrance and state-transition motion without blocking interaction.
- [ ] Run component tests and accessibility checks.

## Task 11: Containerization and operational documentation

**Files:**
- Create: `backend/Dockerfile`, `frontend/Dockerfile`, `docker-compose.yml`, `nginx.conf`
- Create: `README.md`
- Test: `scripts/smoke-test.ps1`

- [ ] Write a smoke script that fails until health, readiness, frontend HTML, and a deterministic offline chat response are available.
- [ ] Implement multi-stage containers, same-origin `/api`, SSE proxy settings, health checks, read-only corpus mount, and persistent data volume.
- [ ] Document setup, ingestion, online/offline modes, model configuration, testing, evaluation, architecture decisions, security, and demo flow.
- [ ] Build containers and run the smoke script.

## Task 12: Full-system verification

**Files:**
- Create: `frontend/e2e/lawagent.spec.ts`, `frontend/playwright.config.ts`
- Modify: documentation only if verification uncovers a mismatch

- [ ] Write E2E tests for initial layout, one complete offline chat, evidence inspection, trace display, responsive navigation, and error recovery.
- [ ] Run the full backend suite with coverage and require at least 80% domain-logic coverage.
- [ ] Run frontend unit tests, TypeScript, lint, production build, and Playwright.
- [ ] Run ingestion against the entire corpus, record success/quarantine/duplicate counts, and build the full index using configured embeddings only after local tests pass.
- [ ] Exercise configured chat and embedding providers with minimal safe calls; record model names, status, latency, and redacted error details.
- [ ] Perform a final secret scan proving credentials appear only in ignored `.env`.
- [ ] Compare implementation against every section of `docs/design.md` and record any intentionally deferred items in README.

