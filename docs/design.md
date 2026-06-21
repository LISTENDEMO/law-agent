# LawAgent 2.0：可评测的多 Agent 法律研究系统

> 文档版本：2.0.0  
> 更新日期：2026-06-21  
> 项目类型：AI Agent / LLM 应用开发面试项目  
> 项目周期：14 天 MVP

---

## 1. 项目定义

### 1.1 项目定位

LawAgent 是一个面向中国大陆现行法律法规的辅助研究系统。用户输入法律问题后，系统通过受控的层级式多 Agent 协作完成事实识别、任务规划、法规检索、法律要件分析、独立审查和引用核验，最终返回带有可验证证据的回答。

本项目重点证明四类能力：

1. 设计真正具有任务委派、工具调用和反馈闭环的多 Agent 系统。
2. 构建适合法律文档结构和法规时效性的高质量 RAG。
3. 通过黄金测试集、消融实验和运行追踪量化系统效果。
4. 在两周内完成可部署、可演示、可解释的工程闭环。

### 1.2 产品边界

系统提供法律信息检索与辅助分析，不替代律师，不作案件结果保证。

MVP 覆盖：

- 法律法规的精确查询、解释与适用性分析。
- 用户事实与法律要件之间的结构化映射。
- 多法条组合问题和有限的多轮澄清。
- 法规版本、效力状态、适用地区和官方来源展示。
- Agent 执行轨迹、引用验证与自动评测。

MVP 不覆盖：

- 用户注册、计费和组织权限。
- 合同文件上传、OCR 和合同审查。
- 裁判文书或法院案例库。
- 自动生成可直接提交的法律文书。
- 多模型负载均衡、独立 Skill 服务和 Kubernetes。

### 1.3 目标用户

- 希望检索和理解中国大陆法律法规的个人。
- 需要辅助研究法规适用范围的企业人员。
- 面试演示中的 AI Agent / LLM 应用开发评审者。

### 1.4 成功标准

| 维度 | MVP 验收目标 |
|---|---|
| 语料处理 | 1032 份现有文档均有明确的成功、重复或隔离状态 |
| 检索质量 | 黄金测试集 Recall@10 ≥ 85% |
| 引用质量 | Citation Precision ≥ 95% |
| 证据完整性 | 所有关键结论均有关联证据或明确的不确定性标记 |
| Agent 稳定性 | 无无限循环；超时、证据不足和模型失败均可降级 |
| 性能 | P95 首 Token 时间目标 < 5 秒，不含上游模型严重抖动 |
| 工程交付 | `docker compose up` 可启动完整系统 |
| 可解释性 | 每次运行可查看规划、委派、工具调用、返工和引用验证结果 |

---

## 2. 设计原则与关键取舍

### 2.1 设计原则

- **证据优先**：模型生成不能替代法律证据，关键结论必须绑定检索证据。
- **受控自主性**：Agent 可规划和调用工具，但受到工具白名单、轮次、预算和 Schema 约束。
- **确定性优先**：引用匹配、权限、限流、数据校验等任务由普通程序完成，不包装成 Agent。
- **先评测再扩展**：每个复杂组件都要通过消融实验证明价值。
- **模块化单体优先**：MVP 保持模块边界，但避免无收益的网络拆分。
- **失败可见**：证据不足时宁可澄清或拒绝确定性结论，也不填补未知信息。

### 2.2 为什么不是六个微服务

项目只有两周交付周期，Agent、RAG、模型适配和会话管理之间调用频繁。过早拆为六个服务会引入重复的数据模型、网络故障、部署和观测成本，却不能显著提高面试展示价值。

MVP 采用前端和后端两个应用。后端内部按领域拆分为 Agent、RAG、评测、数据和模型适配模块；当真实负载或团队边界出现后，再考虑将离线索引和在线推理解耦为独立服务。

### 2.3 为什么它是真正的多 Agent

系统不把固定步骤都称为 Agent。一个组件只有同时具备以下特征，才被定义为 Agent：

- 独立角色、任务目标和上下文。
- 独立的工具权限与输出 Schema。
- 可根据中间结果自主选择下一步工具。
- 有明确停止条件，并能将任务移交给其他 Agent。
- 通过结构化消息参与协作和反馈闭环。

因此，本系统包含一个 Supervisor Agent 和三个 Specialist Agent；安全过滤、引用字符串核对、限流和持久化属于确定性组件。

---

## 3. 总体架构

```text
┌──────────────────────────────────────────────────────────────┐
│                         Next.js Web                          │
│  Chat │ Sources │ Agent Trace │ Evaluation Dashboard        │
└───────────────────────────┬──────────────────────────────────┘
                            │ HTTPS + SSE
┌───────────────────────────▼──────────────────────────────────┐
│                       FastAPI Backend                        │
│                                                              │
│  ┌──────────────── Agent Orchestrator ────────────────────┐  │
│  │ Guardrail → Supervisor ↔ Research / Analysis / Critic │  │
│  │                         ↓                               │  │
│  │              Deterministic Citation Verifier          │  │
│  └────────────────────────────────────────────────────────┘  │
│                                                              │
│  ┌──────────────────── RAG Engine ─────────────────────────┐ │
│  │ Parser │ Metadata Filter │ BM25 │ Vector │ RRF │ Rerank│ │
│  └─────────────────────────────────────────────────────────┘ │
│                                                              │
│  Model Adapter │ Evaluation │ Tracing │ Session Repository   │
└──────────────┬────────────────┬─────────────────┬─────────────┘
               │                │                 │
          SQLite           Chroma/FAISS       File Storage
```

### 3.1 技术选型

| 层级 | MVP 选型 | 选择原因 |
|---|---|---|
| 前端 | Next.js + React + TypeScript | 支持流式 UI、Trace 和评测面板 |
| API | FastAPI + Pydantic | 异步接口和严格 Schema |
| Agent 编排 | LangGraph | 支持条件分支、循环、检查点和状态恢复 |
| 关键词检索 | BM25 | 法律名称、术语和条号的精确匹配能力强 |
| 向量检索 | Chroma 或 FAISS | MVP 本地持久化和快速构建 |
| 融合 | Reciprocal Rank Fusion | 合并 BM25 与向量排序，避免分数量纲问题 |
| 重排序 | Cross-Encoder Reranker | 提高 Top-K 证据精度 |
| 业务存储 | SQLite | 单机 MVP 简单可靠 |
| 部署 | Docker Compose + Nginx | 一条命令启动并保持同源访问 |

技术依赖在实现阶段锁定精确版本，避免仅使用宽泛的最低版本范围导致不可复现。

### 3.2 后端模块边界

```text
backend/
├── api/              # HTTP、SSE、鉴权和请求 Schema
├── agents/           # Supervisor 与 Specialist 定义
├── workflow/         # LangGraph、共享状态、路由和检查点
├── tools/            # Agent 可调用的受控工具
├── rag/              # 解析、索引、检索、融合和重排
├── verification/     # 引用、版本和证据覆盖校验
├── evaluation/       # 数据集、指标、实验运行器
├── repositories/     # SQLite 与文件持久化接口
├── observability/    # Trace、事件和指标
└── model/            # LLM、Embedding、Reranker 适配器
```

模块通过 Python 接口和 Pydantic 模型协作，不通过内部 HTTP 调用。外部 API 不依赖具体向量库或模型提供商。

---

## 4. 多 Agent 协作设计

### 4.1 Agent 角色

#### Supervisor Agent

目标：理解问题、判断信息完整性、拆分任务、选择 Specialist、控制预算并汇总结果。

可执行动作：

- 请求用户补充关键事实。
- 委派法规研究任务。
- 委派法律要件分析任务。
- 请求 Critic 独立审查。
- 根据审查意见定向返工。
- 在证据不足或预算耗尽时停止并降级回答。

Supervisor 不直接访问向量库，也不自行伪造检索结果。

#### Legal Research Agent

目标：找到与问题、时间和地区匹配的有效法规证据。

工具权限：

- `hybrid_search`
- `get_article_context`
- `get_law_version`
- `find_related_articles`

自主循环：制定查询 → 调用检索工具 → 评估结果 → 改写查询。最多三轮，每轮必须说明结构化的检索目标，而不是输出完整思维链。

#### Legal Analysis Agent

目标：将用户事实映射为法律要件，识别成立条件、例外、争议点和缺失信息。

工具权限：

- `read_evidence`
- `get_analysis_template`

输出必须区分用户已陈述事实、合理假设和未知事实，不得把未知事实当作既定事实。

#### Critic Agent

目标：独立检查候选回答的证据支持、遗漏、冲突、过度确定性和风险表达。

工具权限：

- `read_evidence`
- `check_claim_support`
- `check_law_status`

Critic 只能给出审查结论和修订要求，不能直接重写最终答案，避免审查与生成职责混合。

### 4.2 工作流状态机

```text
用户问题
   ↓
确定性安全检查
   ↓
Supervisor
   ├─ 缺少关键事实 → 生成一个聚焦的澄清问题 → 等待用户
   ├─ 简单条文查询 → Research
   ├─ 复杂适用分析 → Research + Analysis
   └─ 高风险问题 → 强制 Critic
                         ↓
                 Supervisor 判断证据
              ┌──────────┴──────────┐
           不充分                  充分
              ↓                     ↓
       改写任务并重试          生成候选回答
       全局最多两次                 ↓
                              Critic 审查
                         ┌───────────┴──────────┐
                       不通过                 通过
                         ↓                     ↓
                  定向返工一次          程序化引用校验
                                                 ↓
                                              最终输出
```

### 4.3 共享状态

```python
class LawAgentState(TypedDict):
    trace_id: str
    session_id: str
    user_query: str
    conversation_summary: str

    jurisdiction: str
    legal_domain: str
    risk_level: Literal["low", "medium", "high"]
    missing_facts: list[str]

    plan: list[Task]
    completed_tasks: list[TaskResult]
    evidence: list[Evidence]
    legal_analysis: LegalAnalysis | None
    draft_answer: str | None

    critique: CritiqueResult | None
    citation_check: CitationCheckResult | None

    retry_count: int
    token_usage: int
    status: WorkflowStatus
```

生产代码中的 `Task`、`Evidence`、`CritiqueResult` 等对象均使用 Pydantic 定义，禁止 Agent 以自由文本替代核心控制字段。

### 4.4 委派协议

每次委派消息必须包含：

```json
{
  "task_id": "task-uuid",
  "agent": "legal_research",
  "objective": "查找劳动合同即时解除的法定条件",
  "inputs": {
    "query": "……",
    "jurisdiction": "中国大陆",
    "as_of_date": "2026-06-21"
  },
  "expected_output": "ResearchResult",
  "stop_conditions": {
    "max_tool_calls": 6,
    "min_evidence_count": 2
  }
}
```

### 4.5 控制与降级

- Supervisor 只能选择白名单 Agent 和动作。
- Research 最多三轮检索，整个工作流最多两次返工。
- 设置每次运行的总 Token、工具调用次数和墙钟时间预算。
- Specialist 输出不符合 Schema 时只允许一次结构修复。
- 上游模型失败时进行有限重试；持续失败则返回已确认资料。
- 证据不足时输出“现有资料不足以形成确定结论”，并指出需要补充的信息。
- 不保存或展示模型完整思维链，只记录计划、动作、工具结果摘要和决策标签。

---

## 5. 法律 RAG 与语料治理

### 5.1 现有语料基线

截至 2026-06-21，`RAG/` 中共有 1032 个文件，总体积约 37.35 MB：

- DOCX：1029 个。
- DOC：3 个，需要单独转换或隔离。
- 文件名带日期提示：932 个。
- 存在仅分隔符不同的疑似重复版本，例如同一法规的 `名称_日期` 与 `名称-日期`。
- 个别文件约 5 MB，可能含图片或特殊格式，需纳入异常处理。

文件名日期只能作为元数据候选，最终发布、生效、修订和失效日期必须从正文或可信元数据校验。

### 5.2 数据治理流水线

```text
raw/ 原始语料（只读）
   ↓
格式检测：DOC / DOCX / 损坏文件
   ↓
正文、标题和法律层级解析
   ↓
Unicode、空白、页眉页脚和编号规范化
   ↓
文件哈希 + 规范化正文哈希去重
   ↓
法规元数据抽取与规则校验
   ↓
质量分级
   ├─ accepted   → normalized/ + indexes
   ├─ review     → 人工审核队列
   └─ quarantine → 隔离并记录原因
```

每次导入生成可重复的数据质量报告：

- 总文件数、成功数、隔离数和失败原因。
- 文件级与内容级重复数量。
- 无法识别法规名称、条号或正文的文档。
- 日期、发布机关、效力状态等元数据缺失情况。
- 解析前后字符数和条文数异常。
- 本次新增、更新、失效和未变化的文档数量。

### 5.3 法律结构化分块

不使用固定 512 字符作为主要分块方式。系统优先识别：

```text
法律 → 编 → 章 → 节 → 条 → 款 → 项
```

主要检索单元为“条”或内容较长时的“款”。每个单元保留父级标题、条号、相邻条文引用和法规版本。固定长度切分只作为无法识别结构时的降级策略，并记录 `parse_mode=fallback`。

规范化记录示例：

```json
{
  "document_id": "npc-gov-cn-civil-code-2020",
  "article_id": "civil-code-2020-article-1079-p2",
  "law_name": "中华人民共和国民法典",
  "article_number": "第一千零七十九条",
  "paragraph_number": 2,
  "content": "……",
  "context_path": ["婚姻家庭编", "离婚"],
  "issuing_authority": "全国人民代表大会",
  "publish_date": "2020-05-28",
  "effective_from": "2021-01-01",
  "effective_to": null,
  "status": "effective",
  "jurisdiction": "中国大陆",
  "source_url": "官方来源 URL",
  "source_file": "中华人民共和国民法典_20200528.docx",
  "version_hash": "sha256...",
  "parse_mode": "article"
}
```

### 5.4 混合检索

```text
用户问题
   ↓
Research Agent 生成 1–3 个检索查询
   ↓
元数据过滤：地区、时间、效力状态、法律领域
   ↓
BM25 Top-20                  Vector Top-20
        └────────────┬────────────┘
                     ↓
                  RRF 融合
                     ↓
           Cross-Encoder Rerank Top-8
                     ↓
    父级标题、相邻条文和关联法条上下文扩展
                     ↓
              Evidence Grader
       sufficient / partial / insufficient
```

RRF 使用排名而非原始分数融合，避免 BM25 和向量相似度量纲不一致。检索结果保留每一阶段的排名和分数，支持调试与消融分析。

### 5.5 法规版本与效力

- 默认只检索问题发生时间对应的有效版本。
- 用户未说明关键时间且不同版本会改变结论时，必须追问。
- 失效法规不参与当前法律结论，只能用于历史比较并显著标记。
- 文档更新后生成新 `version_hash`，保留旧版本以支持历史时间点查询。
- 同名文档不能自动认定为同一版本，需结合正文哈希、日期和发布机关判断。
- `source_url` 应尽量指向发布机关或国家法律法规数据库等权威来源。

### 5.6 防幻觉与证据门控

1. LLM 只能引用当前状态 `evidence` 中存在的 `article_id`。
2. 生成前先形成“关键结论—证据 ID”映射。
3. 每个关键结论至少对应一条证据；无法支持的内容应删除或标记不确定。
4. 确定性校验器核对引用 ID、版本、效力状态和引文原文。
5. Critic 检查结论是否超出证据，但不替代确定性字符串校验。
6. 证据冲突时展示冲突来源并降低置信度，不由模型静默选择。

---

## 6. 输出协议与用户体验

### 6.1 最终回答结构

```json
{
  "summary": "简明结论",
  "analysis": [
    {
      "issue": "争议焦点",
      "conclusion": "结论或不确定性说明",
      "evidence_ids": ["article-id"]
    }
  ],
  "missing_information": [],
  "recommended_actions": [],
  "risk_level": "medium",
  "jurisdiction": "中国大陆",
  "as_of_date": "2026-06-21",
  "disclaimer": "本回答仅供法律信息检索与辅助分析……"
}
```

前端将结构化结果渲染为自然语言段落和可点击的引用标记。引用卡片显示法规名称、条号、原文、发布机关、生效时间、效力状态和来源。

### 6.2 页面组成

- **Chat**：多轮咨询、澄清问题和流式回答。
- **Sources**：证据列表、法条原文和版本信息。
- **Agent Trace**：规划、委派、工具调用、返工原因和耗时。
- **Evaluation Dashboard**：基准指标、消融实验和历史运行对比。
- **Corpus Report**：语料导入、重复、异常和索引状态，仅管理模式可见。

### 6.3 Trace 展示边界

前端展示：

- Agent 名称、任务目标和状态。
- 工具名称、查询参数摘要和结果数量。
- 检索候选、融合排序和最终证据。
- Critic 的结构化问题与返工原因。
- 节点耗时、Token 使用和错误类型。

前端不展示模型隐藏思维链、密钥、内部系统提示或未经脱敏的敏感信息。

---

## 7. API 与流式事件

### 7.1 公共 API

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/v1/chat` | 创建一次 Agent 运行 |
| GET | `/api/v1/chat/{run_id}/events` | 建立或恢复 SSE 流 |
| GET | `/api/v1/sessions/{session_id}` | 获取会话历史 |
| DELETE | `/api/v1/sessions/{session_id}` | 删除会话与相关数据 |
| GET | `/api/v1/sources/{article_id}` | 获取法规证据详情 |
| GET | `/api/v1/health` | 基础健康检查 |

`POST /api/v1/chat` 返回 `run_id`、`session_id` 和事件流地址。幂等键用于避免客户端重试造成重复运行。

### 7.2 管理 API

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/v1/admin/corpus/import` | 导入或增量更新语料 |
| POST | `/api/v1/admin/index/rebuild` | 重建指定索引 |
| GET | `/api/v1/admin/corpus/report` | 获取数据质量报告 |
| POST | `/api/v1/admin/evaluations/run` | 启动评测或消融实验 |
| GET | `/api/v1/admin/evaluations/{run_id}` | 获取评测结果 |

管理 API 必须鉴权，并限制为内部网络或管理模式；不能与公开匿名接口使用相同访问策略。

### 7.3 SSE 事件

```text
run.started
agent.started
agent.completed
tool.started
tool.completed
retrieval.completed
answer.delta
citation.verified
run.completed
run.failed
```

每个事件都包含：

```json
{
  "event_id": "run-id:sequence",
  "run_id": "uuid",
  "sequence": 12,
  "timestamp": "2026-06-21T12:00:00Z",
  "type": "agent.completed",
  "data": {}
}
```

服务端保存有限期事件记录。客户端断线后通过 `Last-Event-ID` 恢复；无法恢复时请求当前运行快照。心跳事件用于检测连接存活。

---

## 8. 数据存储

### 8.1 SQLite 实体

| 实体 | 用途 |
|---|---|
| `sessions` | 会话及保留期限 |
| `messages` | 用户与系统可见消息 |
| `workflow_runs` | 一次 Agent 运行的状态、预算和结果 |
| `agent_steps` | Agent 委派与结构化输出 |
| `tool_calls` | 工具调用、耗时和错误摘要 |
| `citations` | 回答结论与证据映射 |
| `corpus_documents` | 原始文档、哈希和处理状态 |
| `corpus_versions` | 法规版本与效力元数据 |
| `evaluation_runs` | 评测配置、版本和聚合指标 |

所有表使用稳定 UUID，时间统一保存为 UTC。JSON 字段保存前进行 Schema 校验。SQLite 仅由后端进程访问，避免多个容器共享写入导致锁竞争。

### 8.2 文件与索引目录

```text
data/
├── corpus/
│   ├── raw/              # 原始文档，只读
│   ├── normalized/       # 规范化 JSONL
│   ├── review/           # 待人工确认
│   └── quarantine/       # 无法安全入库的文件
├── indexes/
│   ├── vector/
│   └── bm25/
├── evaluation/
│   ├── datasets/
│   └── reports/
├── traces/
├── backups/
└── lawagent.db
```

索引构建采用“生成新版本 → 校验 → 原子切换”的方式，避免在线读取到半成品索引。索引元数据记录语料版本、Embedding 模型、分块算法和构建时间。

---

## 9. 安全、隐私与法律风险

### 9.1 输入与访问控制

- 匿名访问按 IP 和会话限流，并设置每日请求配额。
- 限制消息长度、会话轮数和总上下文大小。
- 管理接口使用独立 API Key 或等价认证。
- 仅 Nginx 暴露公网端口，后端管理能力不直接暴露。
- Agent 工具使用白名单和严格参数 Schema，不能执行任意代码或网络请求。

### 9.2 Prompt Injection 防护

- 法规文档和检索内容一律视为不可信数据，而不是系统指令。
- 系统提示、用户输入和工具结果使用清晰的消息边界。
- 文档中的“忽略前述指令”等文本不能改变 Agent 权限。
- 工具调用由编排器校验，LLM 不能动态创建工具名或扩大权限。
- 对抗测试集覆盖指令注入、虚构法规和诱导泄露系统提示。

### 9.3 隐私

- 进入模型前检测并脱敏身份证号、手机号等敏感字段。
- 日志不记录 API Key、完整身份信息或未经处理的案件材料。
- 会话设置明确保留期限，并提供立即删除接口。
- 面试演示使用合成案情，不使用真实个人案件数据。

### 9.4 风险分级

| 风险等级 | 示例 | 系统行为 |
|---|---|---|
| Low | 法条内容与概念查询 | 正常检索并回答 |
| Medium | 合同解除、劳动争议等适用分析 | 明示事实假设和不确定性 |
| High | 刑事辩护、重大财产处分、人身安全 | 强制 Critic，缩小结论并建议咨询律师或紧急机构 |

---

## 10. 评测体系

> 当前实现基线（2026-06-21）：完整语料 45,552 条且 ID 全部唯一；150 条固定精确法条查询集 Recall@10 为 100%、MRR 为 0.9567、P50/P95 为 18.0/21.2 ms。该集合验证精确引用能力，不替代下述多类别人工黄金集。

### 10.1 黄金测试集

从现有语料构建 150 条带人工标注的测试样本：

| 类别 | 数量 | 验证目标 |
|---|---:|---|
| 精确法条查询 | 30 | 条号、名称和正文召回 |
| 口语化法律咨询 | 30 | Query 改写和语义召回 |
| 多法组合分析 | 25 | 任务规划与多轮检索 |
| 时效与版本问题 | 20 | 时间过滤与历史版本 |
| 信息不足问题 | 15 | 澄清而非猜测 |
| 语料外问题 | 15 | 正确拒答或降级 |
| 对抗与虚构法条 | 15 | 防注入与防幻觉 |

每条样本至少标注：问题、适用时间、地区、标准证据 ID、关键结论、应否追问、应否拒答和风险等级。数据集划分为开发集与冻结测试集，避免针对测试答案反复调参。

### 10.2 指标

| 层级 | 指标 |
|---|---|
| 检索 | Recall@5、Recall@10、MRR、NDCG@10 |
| 生成 | Citation Precision、Citation Completeness、Faithfulness、Answer Relevance |
| Agent | 路由准确率、追问准确率、任务完成率、平均工具调用次数、无效循环率 |
| 工程 | P50/P95 延迟、首 Token 时间、Token 成本、节点失败率、降级成功率 |

Faithfulness 和 Answer Relevance 可以由规则、人工抽检和 LLM Judge 组合评估；LLM Judge 结果不能作为唯一结论，必须固定 Judge Prompt 和模型版本。

### 10.3 消融实验

| 对照实验 | 需要证明的设计价值 |
|---|---|
| Vector vs BM25 vs Hybrid | 混合检索是否提高召回 |
| Hybrid vs Hybrid + Rerank | Reranker 是否提高前排精度 |
| 固定字符分块 vs 法条结构分块 | 结构分块是否改善召回与引用完整性 |
| 单 Agent vs 多 Agent | 协作是否改善复杂问题完成率 |
| 无 Critic vs 有 Critic | 独立审查是否减少无证据结论 |
| 无版本过滤 vs 有版本过滤 | 时效治理是否减少过期法规引用 |

所有实验保存代码版本、语料版本、索引参数、模型、Prompt、随机性配置和原始逐条结果，避免只展示聚合后的“漂亮数字”。

### 10.4 回归门禁

- Recall@10 相对基线下降超过 2 个百分点则阻止发布。
- Citation Precision 低于 95% 则阻止发布。
- 出现无限循环、未授权工具调用或引用不存在的 ID，则视为严重失败。
- 冻结测试集仅用于里程碑验收，日常调试使用开发集。

---

## 11. 可观测性

每次运行分配唯一 `trace_id`，记录：

- Supervisor 的结构化计划和委派关系。
- Agent 开始、结束、状态和 Schema 校验结果。
- 工具调用参数摘要、候选数量、耗时和错误。
- BM25、向量、RRF、Rerank 各阶段排名。
- Critic 的审查标签和返工原因。
- 引用验证结果、Token、首 Token 和总耗时。

核心运行指标：

- 请求量、成功率和错误分类。
- 各 Agent 与工具的 P50/P95 延迟。
- 平均检索轮次、返工率和降级率。
- 单次运行 Token 与估算成本。
- 引用校验失败率和证据不足率。

Trace 默认只面向开发或演示模式，公开用户不能读取其他会话的运行信息。

---

## 12. 部署设计

```text
Internet
   ↓ 80/443
Nginx
├── /        → Next.js
└── /api/*   → FastAPI

Docker Compose
├── frontend
├── backend
└── persistent-volume
```

部署要求：

- 浏览器只访问同源 `/api`，不使用 Docker 内部主机名。
- 只有 Nginx 映射公网端口。
- 后端容器挂载持久化数据卷，原始语料以只读方式挂载。
- `/health` 只表示进程存活；另设内部 readiness 检查索引和数据库状态。
- SSE 关闭代理缓冲，并配置合理的空闲超时。
- `.env` 不进入版本控制，仓库提供 `.env.example`。
- 启动时校验数据库迁移、索引版本和必要密钥，不满足条件则快速失败。

未来出现以下条件时再拆服务：离线索引显著消耗在线资源、向量库需要独立扩缩容、团队形成明确所有权边界，或评测任务需要独立队列。

---

## 13. 异常与恢复策略

| 场景 | 处理方式 |
|---|---|
| LLM 超时 | 指数退避有限重试，随后降级输出已确认资料 |
| Embedding 服务失败 | 保留 BM25 检索能力并标记降级模式 |
| Reranker 失败 | 使用 RRF 排序继续，但记录实验与运行标签 |
| Agent 输出 Schema 错误 | 允许一次结构修复，仍失败则终止该任务 |
| 证据不足 | 最多改写检索两次，之后追问或拒绝确定性结论 |
| 引用校验失败 | 不发布未验证答案，返回生成节点定向修订一次 |
| SSE 断线 | 通过 Last-Event-ID 恢复或获取运行快照 |
| 文档解析失败 | 移入 quarantine，不进入在线索引 |
| 索引重建失败 | 保留并继续使用上一可用索引版本 |
| SQLite 写锁 | 单后端写入、短事务和合理 busy timeout；扩展时迁移 PostgreSQL |

---

## 14. 两周实施计划

| 时间 | 交付物 |
|---|---|
| Day 1–2 | 1032 份语料审计、解析、哈希去重、规范化和质量报告 |
| Day 3–4 | BM25、向量检索、RRF、Rerank、版本过滤和检索基线 |
| Day 5–7 | Supervisor、三个 Specialist、状态机、工具 Schema 和检查点 |
| Day 8 | 引用校验、预算、重试、降级、安全规则和对抗测试 |
| Day 9–10 | Chat、Sources、Agent Trace 前端与 SSE 恢复 |
| Day 11 | 150 条黄金测试集、评测运行器和回归门禁 |
| Day 12 | 六组消融实验、性能分析和关键参数调整 |
| Day 13 | Docker 部署、限流、隐私处理和异常恢复测试 |
| Day 14 | README、架构图、演示脚本、结果报告和面试问答 |

实施顺序坚持先建立最小评测基线，再添加 Rerank、Agent 和 Critic。任何组件若不能在消融实验中证明价值，应简化或删除。

---

## 15. 测试策略

### 15.1 单元测试

- 法条、款项、中文数字条号和父级结构解析。
- 日期、效力状态、哈希和重复识别。
- RRF 排序与元数据过滤。
- Agent 输入输出 Schema 和预算限制。
- 引用 ID、引文原文和结论覆盖校验。
- 风险等级、限流和敏感信息脱敏。

### 15.2 集成测试

- 用户问题到最终回答的完整图执行。
- 信息不足时暂停、追问和恢复。
- Critic 驳回后定向返工。
- Reranker 或 Embedding 失败时降级。
- SSE 事件顺序、断线恢复和终态一致性。
- 增量导入后旧索引原子切换。

### 15.3 端到端测试

- 浏览器提交问题并收到流式回答。
- 点击引用查看正确版本的完整法条。
- Trace 与实际工具调用一致。
- 删除会话后相关公开数据不可再访问。
- 管理接口未认证时不可使用。

---

## 16. 面试演示脚本

演示控制在 8–10 分钟：

1. **问题与数据**：展示 1032 份真实法律法规语料及质量报告。
2. **失败基线**：用一个带时间陷阱或口语表达的问题展示纯向量检索错误。
3. **多 Agent 协作**：展示 Supervisor 拆解任务并分别委派 Research 和 Analysis。
4. **自主工具调用**：Research 因首次证据不足自动改写查询并再次检索。
5. **审查闭环**：Critic 发现结论证据不足，触发一次定向返工。
6. **可信输出**：展示逐结论引用、法规版本、效力状态和官方来源。
7. **量化证据**：展示混合检索、Rerank、结构分块和 Critic 的消融结果。
8. **工程取舍**：解释为何使用模块化单体，以及何时才值得拆分服务。

### 16.1 面试核心表述

> LawAgent 采用受控的层级式多 Agent 架构。Supervisor 动态规划并委派给具备不同目标和工具权限的 Specialist；确定性校验负责安全和引用正确性。系统不是为了展示 Agent 数量，而是通过黄金测试集和消融实验证明多 Agent、混合检索、结构化分块与独立审查分别改善了什么指标。

### 16.2 预期追问

- 为什么不用单 Agent？用复杂问题完成率、工具调用和错误类型的消融结果回答。
- 为什么 Critic 可信？说明其只是风险降低机制，最终引用仍由确定性程序校验。
- 为什么不拆微服务？说明当前负载、交付周期和故障域不支持该复杂度。
- 法规更新怎么办？说明版本哈希、增量导入、旧版本保留和索引原子切换。
- LLM Judge 是否可靠？说明固定版本、规则指标与人工抽检共同使用。
- 如何防止文档注入？说明数据与指令隔离、工具白名单和对抗测试。

---

## 17. 风险与应对

| 风险 | 影响 | 应对 |
|---|---|---|
| DOCX 格式不统一 | 条文解析错误 | 质量分级、fallback 分块、review 与 quarantine |
| 法规元数据不完整 | 时效判断不可靠 | 文件名仅作候选，正文抽取与权威来源校验 |
| 多 Agent 延迟和成本高 | 演示体验下降 | 简单问题走短路径，设置预算并用消融结果决定是否调用 Critic |
| Critic 与生成模型同源 | 审查偏差相关 | 独立上下文、结构化标准、确定性引用校验和人工抽检 |
| 测试集数据泄漏 | 指标虚高 | 开发集与冻结测试集分离，记录实验版本 |
| 匿名公网访问被滥用 | 成本与安全风险 | 限流、配额、输入限制和管理接口隔离 |
| 两周范围过大 | 核心链路不完整 | 严守 MVP 边界，先完成语料—检索—Agent—评测闭环 |

---

## 18. 交付清单

- 可重复的语料导入、规范化、去重和索引脚本。
- 数据质量报告及异常文档清单。
- Supervisor + Research + Analysis + Critic 多 Agent 工作流。
- 混合检索、RRF、Rerank、法规版本过滤和引用验证。
- Chat、Sources、Trace 和 Evaluation Dashboard。
- 150 条黄金测试集、自动评测与消融报告。
- 单元、集成和端到端测试。
- Docker Compose、环境变量示例和部署说明。
- README、架构图、演示脚本和面试问答。

---

## 19. 架构演进条件

MVP 完成后，不按功能愿望直接扩张，而按证据演进：

- SQLite 出现真实并发写瓶颈时迁移 PostgreSQL。
- 本地向量索引无法满足数据量或过滤性能时迁移 Qdrant。
- 离线索引影响在线请求稳定性时拆分 Index Worker。
- Agent 工具生态形成稳定契约后再引入 Skill Registry。
- 有多个可靠模型提供商且故障率数据支持时再实现模型路由。

本设计的最终目标不是做一个功能最多的法律聊天机器人，而是交付一个边界清晰、行为可控、效果可量化、失败可解释的多 Agent LLM 系统。
