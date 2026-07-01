# Arete4BUPT v1.0 · ἀρετή

> 卓越不是天赋，是做出来的。—— 智慧校园 · 个人课程助手

[![Version](https://img.shields.io/badge/version-1.0.0-1a73e8)](https://github.com/Pr1meR1cK/Arete4BUPT/releases/tag/v1.0.0)

## 项目简介

基于 [ACPs 协议族](https://github.com/AIP-PUB/ACPs-Demo-Project) 的多智能体协同系统。1 个 **Leader**（个人课程助手）+ 4 个 **Partner**（选课 / 请假 / 缓考 / 考试提醒），通过 ATR → AIA → ADP → AIP 四层协议全链路互联，已接入北邮 ACPs 智能体互联网平台。

## 系统架构

```
                        用户 (Chat UI / API)
                              │
                              ▼
              ┌───────────────────────────────┐
              │    个人课程助手 (Leader)         │
              │    Port 59210                  │
              │                               │
              │  [1/5] 意图理解                 │
              │  [2/5] ADP 动态发现              │
              │  [3/5] 任务拆解                 │
              │  [4/5] 并行执行                 │
              │  [5/5] 结果整合                 │
              └───────┬───────┬───────┬───────┘
                      │       │       │
          ┌───────────┘       │       └───────────┐
          ▼                   ▼                   ▼
  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
  │  选课助手     │  │  请假助手     │  │  缓考助手     │  │ 考试提醒助手  │
  │  Port 59221  │  │  Port 59222  │  │  Port 59223  │  │  Port 59224  │
  └──────────────┘  └──────────────┘  └──────────────┘  └──────────────┘
          │                   │                   │                   │
          └───────────────────┴───────────────────┴───────────────────┘
```

**编排流程**：Leader 收到用户请求后，依次执行五阶段流水线——意图理解 → ADP 动态发现 → 任务拆解 → 并行调用 Partner → 结果聚合，全程通过 Footprint 大屏实时上报，Chat UI 进度条可视化。

## 目录结构

```
AreteAgents/
├── leader/
│   ├── main.py                  # FastAPI 入口（submit + 轮询 result）
│   ├── static/
│   │   └── index.html           # Chat UI（进度流水线 + 打字机效果）
│   └── assistant/
│       ├── orchestrator.py      # 五阶段主编排器
│       ├── discovery.py         # ADP 动态发现模块
│       ├── aip_client.py        # AIP JSON-RPC 客户端
│       ├── llm_client.py        # LLM 调用封装
│       └── session.py           # 会话 / 任务状态管理
├── partners/
│   ├── course_selector/         # 选课助手（已注册 AIC）
│   ├── leave_request/           # 请假助手
│   ├── exam_deferral/           # 缓考助手（已注册 AIC）
│   └── exam_reminder/           # 考试提醒助手
│       ├── main.py              # FastAPI + /rpc AIP 端点
│       ├── acs.json             # ACS 能力描述
│       ├── atr_client.py        # ATR 注册客户端
│       └── footprint_sdk.py     # Footprint 上报 SDK
├── footprint_sdk.py             # 全局 Footprint 追踪 SDK
├── ngrok.yml                    # ngrok 公网暴露配置
└── README.md
```

## 智能体能力矩阵

| Agent | 角色 | AIC | 核心能力 |
|-------|------|-----|----------|
| 个人课程助手 | Leader | `R1JUQE.821HRL.1.0YVV` | 意图理解、ADP 发现、任务拆解、多 Partner 调度、结果整合 |
| 选课助手 | Partner | `T1DSWF.UEFEWI.1.0Z6R` | 课程查询、方向推荐、先修检查、容量查询、选课规划 |
| 请假助手 | Partner | `HBQ3SF.F7JHGG.1.07HK` | 请假申请生成、审批流程指引、病假/事假/公假分类、材料清单 |
| 缓考助手 | Partner | `6CMY1O.ZTFJB0.1.0HE0` | 缓考资格判断、材料清单、申请步骤、场景适配 |
| 考试提醒助手 | Partner | `E3GP7C.E6A4I1.1.0HJ7` | 考试时间查询、冲突检测、DDL 提醒、考场信息推送 |

## 核心特性

- **五阶段编排引擎**：意图 → ADP 发现 → 任务拆解 → 并行执行 → 结果聚合，每阶段终端实时打印 `[1/5]~[5/5]`
- **ADP 动态发现**：Leader 运行时向 ADP 服务器查询匹配 Agent，获取真实 endpoint 后直接调用，无需硬编码地址
- **跨组协同**：通过 ngrok 将本地 Partner 暴露为公网 HTTPS，其他组 Leader 可通过 ADP 发现并调用
- **Chat UI 进度可视化**：前端轮询 + 进度流水线 + 打字机效果，消除长时间等待感知
- **Footprint 全链路追踪**：每次 Agent 协同调用自动上报 Footprint 大屏，审计链路完整可追溯
- **ACS 配置驱动**：Agent 能力通过结构化 JSON 描述，新增 Partner 不改 Leader 代码

## 技术栈

- **Agent 框架**: Python 3.10+ / FastAPI / Uvicorn
- **协议**: ACPs 协议族 v02.00 (ATR / AIA / ADP / AIP)
- **安全**: mTLS 双向认证
- **可视化**: Footprint 态势感知大屏 + Chat UI 进度流水线
- **公网暴露**: ngrok
- **协作**: Git + GitHub

## 服务器地址

| 服务 | 地址 |
|------|------|
| Footprint 大屏 | http://117.74.66.90:8006/ |
| 注册服务器 (ATR) | http://117.74.66.90:8002/ |
| 发现服务器 (ADP) | http://117.74.66.90:8005/ |
| 认证服务器 (CA) | http://117.74.66.90:8003/ |

## 快速开始

### 前置条件

- Python 3.10+
- Git
- 已安装依赖：`pip install -r requirements.txt`
- 各 Partner 已完成 ATR 注册（首次使用需运行 `python atr_client.py`）

### 启动步骤

```bash
# 1. 启动 4 个 Partner（每个在独立终端，或都加 & 后台运行）
cd partners/course_selector && python -m uvicorn main:app --host 0.0.0.0 --port 59221 &
cd partners/leave_request   && python -m uvicorn main:app --host 0.0.0.0 --port 59222 &
cd partners/exam_deferral   && python -m uvicorn main:app --host 0.0.0.0 --port 59223 &
cd partners/exam_reminder   && python -m uvicorn main:app --host 0.0.0.0 --port 59224 &

# 2. 启动 Leader（前台，显示编排日志）
cd leader && python -m uvicorn main:app --host 0.0.0.0 --port 59210

# 3. 浏览器打开 Chat UI
#    http://localhost:59210/
```

> 端口冲突时先清理：`lsof -ti:59210,59221,59222,59223,59224 | xargs kill -9`（macOS/Linux）。Windows 请在任务管理器中结束占用端口的进程。

## 参考资料

- [ACPs-Demo-Project 旅游助手示例](https://github.com/AIP-PUB/ACPs-Demo-Project)
- [ACPs 参考示例汇总](https://github.com/AIP-PUB/ACPs-Demo-Project/wiki/ACPs-%E5%8F%82%E8%80%83%E7%A4%BA%E4%BE%8B%E6%B1%87%E6%80%BB)

## 版本历程

| 版本 | 日期 | 里程碑 |
|------|------|--------|
| **v1.0.0** | 2026-05-24 | 4 Partner 全注册 · 五阶段编排 · Chat UI · Footprint · 跨组协同 |
| v0.1.0 | 2026-05-12 | 项目启动 · Leader + 3 Partner 骨架搭建 |

> **v2.0 规划中**：Partner 间 ADP 互联、真实校园 API 对接、Chat UI 风格升级、跨平台兼容（macOS / Windows / Linux）。持续迭代，敬请期待。
