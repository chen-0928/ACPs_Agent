# 缓考助手 Partner Agent

> ACP 实训营 · 第一组 · Partner Agent
> 高校缓考申请助手 — 提供资格判断、材料清单、申请步骤、截止日期、多门处理、场景适配六大能力。

![status](https://img.shields.io/badge/status-running-success) ![python](https://img.shields.io/badge/python-3.10+-blue) ![protocol](https://img.shields.io/badge/protocol-AIP%2FADP%2FATR%2FAIA-purple)

## ✨ 功能特性

| Skill ID | 名称 | 示例问题 |
|----------|------|---------|
| `eligibility_check` | 缓考资格判断 | "我生病了能申请缓考吗？" |
| `materials_list` | 缓考材料清单 | "缓考需要提交什么材料？" |
| `application_guide` | 申请步骤指引 | "缓考怎么申请？" |
| `deadline_query` | 截止日期查询 | "缓考截止日期？" |
| `multi_exam_defer` | 多门考试缓考 | "我有三门要缓考" |
| `scenario_adapt` | 常见场景适配 | "考试当天突然发烧怎么办？" |

## 🏗 项目结构

```
deferred_exam_agent/
├── main.py              # FastAPI 主程序 + 所有端点
├── models.py            # AIP 协议数据模型 (TaskCommand/TaskResult)
├── knowledge.py         # 缓考知识库 + 意图路由
├── llm_client.py        # LLM 调用 + 失败降级
├── memory.py            # 多轮会话记忆
├── atr_client.py        # ATR 注册脚本 → 获取 AIC
├── aia_client.py        # AIA 证书申请 → 生成 mTLS 证书
├── footprint.py         # Footprint 上报中间件
├── demo_leader.py       # Leader 模拟器（演示整链路）
├── acs.json             # Agent 能力描述
├── config.toml          # 配置（LLM/端口/证书/AIC）
├── prompts.toml         # 三阶段 Prompt
├── requirements.txt     # Python 依赖
├── static/index.html    # Web Chat UI
├── tests/
│   ├── test_knowledge.py   # 知识库单元测试 (14 项)
│   └── test_rpc.py         # /rpc 端点集成测试 (8 项)
├── certs/               # mTLS 证书 (AIA 生成)
└── logs/footprint.jsonl # Footprint 本地日志
```

## 🚀 快速开始

### 1. 安装依赖

```powershell
pip install -r requirements.txt
```

### 2. ATR 注册（获取 AIC）

```powershell
python atr_client.py
```

> 真实 ATR 服务器不可达时自动生成 mock AIC 用于本地开发。

### 3. AIA 申请 mTLS 证书

```powershell
python aia_client.py
```

> 生成 `certs/ca.crt` `certs/agent.crt` `certs/agent.key`

### 4. 配置 LLM (可选)

编辑 `config.toml`，填入 `llm.api_key`。不填则自动使用本地知识库。

### 5. 启动 Agent

```powershell
python main.py
```

启动后访问：
- **Web UI**:   http://localhost:8001/
- **RPC 端点**: POST http://localhost:8001/rpc
- **ACS**:      GET  http://localhost:8001/acs
- **发现**:     GET  http://localhost:8001/discover
- **Footprint**: GET http://localhost:8001/footprint
- **健康**:     GET  http://localhost:8001/health

### 6. 运行测试

```powershell
# 知识库单元测试 (14 项)
python tests/test_knowledge.py

# /rpc 集成测试 (8 项) - 需先启动 server
python tests/test_rpc.py

# Leader → Partner 完整流程演示
python demo_leader.py
```

## 📡 API 文档

### POST `/rpc` — AIP 协议入口

**Request (TaskCommand):**
```json
{
  "task_id": "task-001",
  "sender_id": "leader-agent",
  "receiver_id": "deferred-exam-partner",
  "intent": "",
  "query": "因病无法参加考试，怎么申请缓考？",
  "context": { "session_id": "user-001" }
}
```

**Response (TaskResult):**
```json
{
  "task_id": "task-001",
  "agent_id": "deferred-exam-partner",
  "status": "done",
  "answer": "## 缓考申请流程\n...",
  "metadata": {
    "intent": "steps",
    "reason": "illness",
    "skills_used": ["application_guide"],
    "source": "local_knowledge_base",
    "session_id": "user-001"
  },
  "timestamp": "2026-05-19T15:30:00"
}
```

### GET `/acs` — 能力描述

返回完整 `acs.json` + 当前 AIC。

### GET `/discover` — ADP 发现端点

供 Leader 通过 ADP 协议发现本 Agent。

### GET `/footprint?limit=50` — Footprint 上报记录

返回最近 N 条 RPC 调用痕迹（task_id / sender / 耗时 / 状态等）。

## 🎯 ACP 实训营交付物清单

| # | 交付物 | 状态 | 文件 |
|---|--------|------|------|
| 1 | Python 代码 (FastAPI)，可独立运行 | ✅ | `main.py` 等 |
| 2 | acs.json 能力描述文件 | ✅ | `acs.json` |
| 3 | prompts.toml 三阶段 Prompt | ✅ | `prompts.toml` |
| 4 | config.toml 配置文件 | ✅ | `config.toml` |
| 5 | AIC (通过 ATR 注册获得) | ✅ | `atr_client.py` → 自动写入 config |
| 6 | mTLS 证书 (通过 CA 认证获得) | ✅ | `aia_client.py` → `certs/` |
| 7 | Footprint 上报接入 | ✅ | `footprint.py` 中间件 |

## 🔬 D2 知识对应

| D2 学习内容 | 在本项目中的实现 |
|------------|------------------|
| ATR 可信注册 | `atr_client.py` — 向注册服务提交 acs.json，获取 AIC |
| AIA 身份认证 | `aia_client.py` — 生成 mTLS 双向证书 |
| ADP 智能体发现 | `/discover` 端点 + `acs.json` |
| AIP 能体交互 | `/rpc` 端点 + TaskCommand/TaskResult 模型 |
| ACS 能力描述 | `acs.json` — 6 个 skills 配 tags + examples |

## 💡 设计亮点

1. **本地兜底**：无 LLM 时通过 `knowledge.py` 仍可正确回答常见问题，测试覆盖 14 项。
2. **三阶段 Prompt**：理解 → 规划 → 执行，对应 `prompts.toml` 的三个 section。
3. **多轮记忆**：通过 `context.session_id` 启用会话记忆，自动延续上下文（demo 中第二轮"需要哪些材料？"会基于第一轮的"我生病了"返回因病缓考材料）。
4. **失败降级**：LLM 超时/报错时自动切到本地知识库，业务永不中断。
5. **可观测**：Footprint 中间件记录每次调用，本地落盘 + 可选远程上报。

## 📜 License

MIT
