# 这是一个中间层
from typing import TypedDict

class AgentState(TypedDict):
    """
    工作流全局状态 —— 在整个流水线的各个 Agent 之间流转。

    每个字段旁的注释标注了「谁来读 / 谁来写」。
    """
    # ── 用户输入 ──
    user_request: str
    # 写: 用户   读: Planner

    # ── Planner 产出 ──
    tasks: list[dict]
    # 写: Planner   读: Coder, 编排引擎
    # 每个 task 格式: {"id": 1, "title": "...", "description": "...", "expected_output": ["main.py"]}

    # ── 进度控制 ──
    current_task_index: int
    # 写: 编排引擎   读: 编排引擎, Coder
    # 指向 tasks[current_task_index]，表示当前正在执行第几个任务

    retry_count: int
    # 写: 编排引擎   读: 编排引擎
    # 当前任务的已重试次数。每次 Reviewer/Tester 不通过 +1，到 max_retries 则放弃当前任务

    max_retries: int
    # 写: 初始化时   读: 编排引擎
    # 固定值 3

    # ── Coder 产出 ──
    file_changes: list[str]
    # 写: Coder   读: Reviewer, Tester
    # Coder 本轮修改过的文件路径列表

    # ── Reviewer 产出 ──
    review_report: dict
    # 写: Reviewer   读: 编排引擎, Coder（回退时）
    # 格式: {"verdict": "pass"|"fail", "issues": [...], "summary": "..."}

    # ── Tester 产出 ──
    test_report: dict
    # 写: Tester   读: 编排引擎, Coder（回退时）
    # 格式: {"passed": 0, "failed": 0, "failures": [...], "summary": "..."}

    context: str
    # 历史经验文本（写：编排器，读：Planner）