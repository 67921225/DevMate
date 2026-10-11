# DevMate — 基于 LangGraph 的多智能体编程助手

输入一句自然语言需求，系统自动调度 **Planner（规划）→ Coder（编码）→ Reviewer（审查）→ Tester（测试）** 四个 Agent 协作，完成「需求分析 → 任务拆解 → 代码生成 → 审查 → 测试 → 失败回退修复」的完整开发闭环，并通过 WebSocket 实时推送整个执行过程。

## 架构

```
┌──────────────┐
│  自然语言需求  │
└──────┬───────┘
       │ POST /tasks
       ▼
┌──────────────────────────────────────────────────┐
│              FastAPI 后端（backend/）              │
│  ┌────────────────┐      ┌───────────────────┐   │
│  │  REST 路由      │      │ WebSocket /ws/tasks│   │
│  │ projects / tasks│────▶│  实时推送事件流      │   │
│  └───────┬────────┘      └─────────▲─────────┘   │
│          │ 后台线程启动              │              │
│          ▼                         │              │
│  ┌─────────────────────────────────┴──────────┐   │
│  │       orchestrator + EventBus（事件总线）    │   │
│  │       线程跑流水线 → 事件推送 + 落库 SQLite   │   │
│  └─────────────────────┬──────────────────────┘   │
└────────────────────────┼──────────────────────────┘
                         │
                         ▼
┌──────────────────────────────────────────────────┐
│          LangGraph 编排引擎（Agent/）              │
│   Planner → Coder → Reviewer → Tester → 下一任务   │
│                 ▲         │          │            │
│                 └─────────┴─失败回退──┘  (最多3次)  │
└────────┬─────────────────────────────┬───────────┘
         │ 结构化输出 / 工具调用          │
         ▼                             ▼
┌──────────────────┐        ┌──────────────────────┐
│   DeepSeek (LLM) │        │  工具层（安全沙箱）     │
│  function-calling│        │  read/write/exec/…    │
└──────────────────┘        └──────────┬───────────┘
                                       │ 路径校验限定在
                                       ▼
                             ┌─────────────────────┐
                             │ 工作空间（每任务隔离）  │
                             └─────────────────────┘
```

## 核心特性

- **多智能体编排**：LangGraph `StateGraph` 把 4 个角色 Agent 串成流水线，通过「条件边」实现审查失败 / 测试失败时的自动回退修复（最多重试 3 次），并带死循环保护。
- **结构化输出**：把期望结果定义成 Pydantic 模型并转成 JSON Schema，用 function-calling 强制模型按固定结构输出——**用机制而非提示词保证格式**。
- **安全工具层**：文件读写（路径遍历拦截 + 软链接解析）、Shell 执行（命令白名单 + 危险模式拦截 + 30s 超时）、依赖安装（白名单控制），防止 Agent 越权操作。
- **过程透明**：事件总线把 Agent 的思考、工具调用、状态变化逐条落库 SQLite，并通过 WebSocket 实时推送给客户端。
- **后台线程编排**：后台线程运行流水线，`loop.call_soon_threadsafe` 桥接异步事件循环，实现「实时推送 + 落库」双写。

## 技术栈

| 层 | 选型 |
|---|---|
| 编排 | LangGraph（StateGraph + 条件边） |
| 工具 | LangChain `@tool` |
| LLM | DeepSeek（OpenAI 兼容 SDK，可插拔多模型） |
| 后端 | FastAPI + WebSocket |
| 数据 | SQLAlchemy 2.0 + SQLite |
| 数据校验 | Pydantic v2 |
| 评估 | pytest + 自研评估脚本 |

## 快速开始

### 1. 安装依赖

```bash
pip install -r backend/requirements.txt
```

### 2. 配置密钥

```bash
cp .env.example .env
# 编辑 .env，填入真实 key（.env 已被 .gitignore 忽略，切勿提交）：
#   DEEPSEEK_API_KEY   必填，在 https://platform.deepseek.com 申请
#   DEEPSEEK_API_URL   可选，默认官方地址
```

### 3. 启动后端

```bash
uvicorn backend.app.main:app --reload
```

### 4. 创建项目并派发任务

| 接口 | 说明 |
|---|---|
| `POST /projects` | 创建项目（自动生成独立工作空间目录） |
| `POST /tasks` | 提交自然语言需求，后台线程启动流水线 |
| `GET /tasks/{task_id}` | 查询任务状态 |
| `WS /ws/tasks/{task_id}` | 订阅该任务的实时事件流 |

## 项目结构

```
多智能体编程助手/
├── LLM_using.py            # LLM 调用层（抽象基类 + 结构化输出）
├── tools.py                # 工具层（7 个带安全防护的工具）
├── Agent/
│   ├── state.py            # 共享状态定义（各 Agent 间流转）
│   ├── schemas.py          # Pydantic 结构化输出模型
│   ├── Agentloop.py        # 单 Agent 循环（ReAct 式）
│   ├── planner.py          # Planner：需求 → 子任务拆解
│   ├── coder.py            # Coder：写代码 / 修代码
│   ├── reviewer.py         # Reviewer：代码审查（含 ruff 静态检查）
│   ├── tester.py           # Tester：生成并运行 pytest 测试
│   └── orchestration.py    # LangGraph 编排引擎（图 + 条件边）
├── backend/
│   ├── requirements.txt
│   └── app/
│       ├── main.py         # FastAPI 入口
│       ├── config.py       # 路径 / 数据库配置
│       ├── database.py     # SQLAlchemy engine / session
│       ├── models/         # ORM 模型（project / task / agent_log）
│       ├── schemas/        # Pydantic 请求响应模型
│       ├── routers/        # project / task / ws 路由
│       └── services/       # orchestrator（后台线程）+ event_bus
├── eval/
│   ├── planner_eval.py     # Planner 规划能力评估
│   ├── end_to_end_eval.py  # 端到端流水线评估
│   ├── results/            # 评估结果 JSON（证据，保留）
│   └── workspaces/         # 评估工作区（LLM 生成，已 gitignore）
├── .env.example            # 密钥模板（真实 .env 不入库）
└── 项目进程.md / 项目策划书.md
```

## 评估

用自研评估脚本对核心能力做量化验证：

- **Planner 规划评估**：5 个递进难度任务，拆解成功率 **100%**，平均每个需求拆解 **4.6** 个子任务（`eval/results/planner_eval_*.json`）。
- **端到端评估**：3 个递进难度任务跑完整流水线（真实写文件、跑 pytest、调 LLM），done 率 **100%**，平均测试通过率 **99%**（累计 481 个测试通过、2 个失败）（`eval/results/e2e_*.json`）。

```bash
python eval/planner_eval.py
python eval/end_to_end_eval.py
```

## 已知局限 / Roadmap

- **前端未接入**：事件已通过 WebSocket 实时推送，前端页面尚未开发（当前可用 `wscat` 等工具订阅 `/ws/tasks/{task_id}` 查看）。
- **单用户 MVP**：`user_id` 硬编码为 1，表结构已预留字段，接入登录时只改查询条件。
- **单机存储**：SQLite，适合单机 MVP；多用户并发写可平滑迁到 MySQL / PostgreSQL。

## 安全设计

工具层是 Agent 接触文件系统/命令行的唯一入口，做了三层防护：

1. **路径遍历拦截**：`abspath`（消 `..`）+ `realpath`（消软链接）+ `commonpath` 前缀校验，读写操作严格限制在工作空间内。
2. **命令白名单**：Shell 执行仅允许 `python / pytest / pip / ls / cat / echo / ruff / pylint`，并拦截 `rm`、`sudo`、`curl`、管道、重定向等危险模式。
3. **超时与限额**：命令执行 30s 超时、依赖安装 120s 超时，防止挂起；工具返回内容截断，防止 Agent 上下文溢出。
