# 校园请假助手 leave_request_agent

校园请假助手 `leave_request_agent` 是一个面向北邮校园场景的 Partner Agent，支持病假、事假、公假办理指引、材料清单生成、审批流程说明和请假申请草稿生成。当前版本优先保证本地 demo 可运行，同时保留 ACPs 接入、ACS 能力描述、Footprint 上报和 Leader Agent RPC 调用结构。

本 Agent 使用“参考高校常见学生事务流程，按北邮校园场景模拟”的规则，不代表北京邮电大学官方政策。

网页 `/` 只是本地测试面板，方便手动填写表单查看效果；真实多智能体协作不依赖网页 UI，而是由 Leader Agent、个人课程助手或其他 Partner Agent 直接调用 `POST /rpc` 完成。

## 后端 Agent 核心接口

| 接口 | 用途 | 是否核心 |
|---|---|---|
| `POST /rpc` | 多智能体调用入口，接收 `TaskCommand`，返回结构化 `TaskResult` | 是 |
| `GET /acs` | 返回 `acs.json`，用于能力发现、服务检索和调试 | 是 |
| `GET /health` | 本地运行和接入状态检查 | 辅助 |
| `POST /leave/analyze` | 单独分析请假需求，方便本地测试 | 辅助 |
| `POST /leave/draft` | 单独生成请假草稿，方便本地测试 | 辅助 |
| `GET /` | 本地测试面板，不参与真实多智能体协作 | 仅 demo |

`/rpc` 收到外部 Agent 调用时，如果请求中包含 `source_agent_name` 和 `source_aic`，会通过 `footprint_client.py` 调用 `notify_call(...)` 上报一次调用轨迹。Footprint 上报失败不会导致主任务失败，只会写入 warning。

## 评分项对照表

| 评分点 | 本 Agent 对应实现 |
|---|---|
| 校园特定应用智能体 | 面向校园请假场景，支持病假、事假、公假 |
| 可被个人助手调用 | 提供 POST /rpc 接口 |
| 多智能体协作 | 支持 Leader Agent 调用并返回结构化 TaskResult |
| ACPs 接入准备 | 提供 acs.json、config.example.toml、AIC 占位 |
| Footprint 上报 | footprint_client.py 封装 notify_call |
| 跨组服务提供 | 外部 Agent 可根据 ACS 发现并调用 /rpc |
| 用户体验 | 支持缺失信息追问、材料清单、流程说明、申请草稿 |
| 技术创新 | 三阶段处理链 + 规则引擎 + LLM 可插拔 + 本地 demo 兼容 |

## 本地运行方式

```bash
pip install -r requirements.txt
cd partners/leave_request
cp config.example.toml config.toml
uvicorn main:app --host 0.0.0.0 --port 59222 --reload
```

Windows PowerShell 可使用：

```powershell
Copy-Item config.example.toml config.toml
uvicorn main:app --host 0.0.0.0 --port 59222 --reload
```

如果 PowerShell 输出中文乱码，先执行：

```powershell
chcp 65001
[Console]::InputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
```

PowerShell 里建议使用 `curl.exe` 查看原始 JSON，不要使用 `curl`，因为 `curl` 默认是 `Invoke-WebRequest` 的别名。

## 测试命令

健康检查：

```bash
curl http://127.0.0.1:59222/health
```

Windows PowerShell：

```powershell
curl.exe http://127.0.0.1:59222/health
curl.exe http://127.0.0.1:59222/acs
```

能力发现：

```bash
curl http://127.0.0.1:59222/acs
```

网页 demo：

```text
http://127.0.0.1:59222/
```

说明：网页 demo 只是本地测试面板。其他 Agent 不需要打开网页，直接调用 `/rpc` 即可。

## 其他 Agent 直接调用示例

下面的请求模拟“个人课程助手”直接调用“校园请假助手”，不经过网页 UI。

Windows PowerShell 请使用 `curl.exe`，不要使用 `curl`，因为 PowerShell 中 `curl` 默认是 `Invoke-WebRequest` 的别名。

```powershell
curl.exe -X POST "http://127.0.0.1:59222/rpc" `
  -H "Content-Type: application/json" `
  -d "{`"task_id`":`"agent-call-001`",`"source_agent_name`":`"个人课程助手`",`"source_aic`":`"1.2.156.3088.leader`",`"target_agent_name`":`"校园请假助手`",`"target_aic`":`"PLEASE_REPLACE_WITH_REAL_AIC`",`"user_id`":`"student-001`",`"command`":`"我因发烧，想从2026-05-14到2026-05-16请3天病假，请帮我生成材料清单、审批流程和请假申请。`",`"context`":{`"student_name`":`"张三`",`"student_id`":`"2024000101`",`"college`":`"信息与通信工程学院`",`"leave_type`":`"sick_leave`",`"reason`":`"发烧`",`"start_time`":`"2026-05-14`",`"end_time`":`"2026-05-16`",`"duration`":`"3天`"}}"
```

等价的 Bash / macOS / Linux 示例：

```bash
curl -X POST "http://127.0.0.1:59222/rpc" \
  -H "Content-Type: application/json" \
  -d '{
    "task_id": "agent-call-001",
    "source_agent_name": "个人课程助手",
    "source_aic": "1.2.156.3088.leader",
    "target_agent_name": "校园请假助手",
    "target_aic": "PLEASE_REPLACE_WITH_REAL_AIC",
    "user_id": "student-001",
    "command": "我因发烧，想从2026-05-14到2026-05-16请3天病假，请帮我生成材料清单、审批流程和请假申请。",
    "context": {
      "student_name": "张三",
      "student_id": "2024000101",
      "college": "信息与通信工程学院",
      "leave_type": "sick_leave",
      "reason": "发烧",
      "start_time": "2026-05-14",
      "end_time": "2026-05-16",
      "duration": "3天"
    }
  }'
```

期望返回：

- `status = success`
- `data.leave_type = sick_leave`
- `data.required_materials` 包含诊断证明或病历
- `data.approval_flow` 包含辅导员、学院、任课教师
- `data.draft_application` 是可复制的中文请假申请草稿

病假成功案例：

```bash
curl -X POST http://127.0.0.1:59222/rpc \
  -H "Content-Type: application/json" \
  -d '{
    "task_id": "test-sick-001",
    "source_agent_name": "个人课程助手",
    "source_aic": "1.2.156.3088.leader",
    "target_agent_name": "校园请假助手",
    "target_aic": "1.2.156.3088.leave",
    "user_id": "student-001",
    "command": "我发烧了，想从5月14日到5月16日请三天病假，帮我看看需要什么材料并写一份请假申请。",
    "context": {
      "student_name": "张三",
      "student_id": "2024000101",
      "college": "信息与通信工程学院"
    }
  }'
```

期望：`status = success`，`leave_type = sick_leave`，材料包含诊断证明或病历，流程包含辅导员、学院、任课教师，草稿完整。

信息缺失案例：

```bash
curl -X POST http://127.0.0.1:59222/rpc \
  -H "Content-Type: application/json" \
  -d '{
    "task_id": "test-missing-001",
    "source_agent_name": "个人课程助手",
    "source_aic": "1.2.156.3088.leader",
    "target_agent_name": "校园请假助手",
    "target_aic": "1.2.156.3088.leave",
    "user_id": "student-002",
    "command": "我想请假",
    "context": {}
  }'
```

期望：`status = need_more_info`，`missing_fields` 包含姓名、学号、请假原因、开始时间、结束时间等，`next_questions` 生成追问。

公假参加比赛案例：

```bash
curl -X POST http://127.0.0.1:59222/rpc \
  -H "Content-Type: application/json" \
  -d '{
    "task_id": "test-official-001",
    "source_agent_name": "个人课程助手",
    "source_aic": "1.2.156.3088.leader",
    "target_agent_name": "校园请假助手",
    "target_aic": "1.2.156.3088.leave",
    "user_id": "student-003",
    "command": "我要参加大学生创新创业比赛，5月20日到5月22日和课程冲突，想申请公假，请帮我生成材料清单和请假申请。",
    "context": {
      "student_name": "李四",
      "student_id": "2024000201",
      "college": "信息与通信工程学院",
      "activity_name": "大学生创新创业比赛",
      "organizer": "学校创新创业学院"
    }
  }'
```

期望：`status = success`，`leave_type = official_leave`，材料包含活动通知、参赛证明、指导老师或组织单位证明，流程包含组织单位确认、辅导员审核、学院审批、通知任课教师，草稿为公假申请草稿。

运行单元测试：

```bash
pytest partners/leave_request/tests
```

## 如何替换真实 ACPs 信息

- 将 `config.toml` 中 `agent.aic` 替换为 ATR 注册获得的真实 AIC。
- 将 `cert_file` / `key_file` / `ca_file` 替换为 CA 认证生成的证书路径。
- 将 `footprint_url` 替换为实训平台提供的大屏上报地址。
- 真实接入后可将 `local_demo_mode` 设为 `false`。
- 也可用环境变量 `LEAVE_AGENT_AIC`、`LEAVE_AGENT_FOOTPRINT_URL` 覆盖配置。

## 注意事项

本 Agent 不直接提交请假申请，不代表北邮官方审批系统，只提供实训场景下的请假办理指引和申请草稿。具体要求以辅导员、学院和学校实际系统通知为准。
