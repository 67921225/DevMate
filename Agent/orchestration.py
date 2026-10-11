"""
第4步：Multi-Agent 编排引擎
基于 LangGraph StateGraph 将 Planner / Coder / Reviewer / Tester 串联为自动化开发流水线。
"""

from typing import Literal
from langgraph.graph import StateGraph, END
from Agent.coder import coder_node
from Agent.planner import planner_node
from Agent.reviewer import reviewer_node
from Agent.tester import tester_node
from Agent.state import AgentState

# ── 路由函数（条件边）──

def after_reviewer(state: AgentState) -> Literal["coder", "tester"]:
    """
    Reviewer 之后的决策：
      - pass → 进入 Tester
      - fail → 回退到 Coder（携带修复建议）
    """
    review = state.get("review_report", {})

    # 可以直接改 state
    if review.get("verdict") == "fail": 
        return "coder"
    return "tester"


def after_tester(state: AgentState) -> Literal["coder", "next_or_end"]:
    """
    Tester 之后的决策：
      - pass → 下一个任务（如果没有更多任务则结束）
      - fail → 回退到 Coder（携带错误信息）
    """
    test = state.get("test_report", {})
    
    # 为什么把判断从 "failed == 0" 改成 "passed > 0 and failed == 0"：
    # pytest 一个测试都没收集到时，tester 会得到 passed=0、failed=0。
    # 旧条件 "failed == 0" 会把它误判成"全部通过"，让流水线把"根本没
    # 测到任何东西"当成成功。必须要求"确实有测试通过、且没有失败"才放行，
    # 这样"0 测试运行"会正确走回退分支，而不是带着假成功结束。
    if test.get("passed", 0) > 0 and test.get("failed", 0) == 0:
        # 有测试真正跑过且全部通过，进入下一个任务
        return "next_or_end"  
    return "coder"


def next_task_router_node(state: AgentState) -> AgentState:
    """
    路由节点（不做 LLM 调用，只做状态操作）。
    当前任务完成后，将任务索引 +1，重置重试计数。
    """
    state["current_task_index"] = state.get("current_task_index", 0) + 1
    state["retry_count"] = 0
    state["file_changes"] = []
    state["review_report"] = {}
    state["test_report"] = {}
    return state


def after_coder(state: AgentState) -> Literal["reviewer", "skip_to_end"]:
    """
    Coder 之后的决策：
      - 正常 → 进入 Reviewer
      - 重试次数超限 → 放弃当前任务，跳到下一个
    """
    if state["retry_count"] >= state["max_retries"]:
        return "skip_to_end"
    else:
        return "reviewer"


def next_task_or_end(state: AgentState) -> Literal["coder", "end"]:
    """
    判断是否还有未完成的任务：
      - 有 → 回到 Coder（处理下一个任务）
      - 无 → 结束工作流
    """
    if state["current_task_index"] < len(state["tasks"]):
        return "coder"
    return "end"


# ── 构建图 ──

def build_graph() -> StateGraph:
    """
    构建 LangGraph StateGraph，定义节点和边。

    工作流拓扑:
        START → planner → coder → reviewer ─┬─ pass → tester ─┬─ pass → next_task ─┬─ 有任务 → coder
                                             │                  │                     │
                                             └─ fail → coder   └─ fail → coder       └─ 无任务 → END
    """
    graph = StateGraph(AgentState)

    # 1. 添加节点
    graph.add_node("planner", planner_node)
    graph.add_node("coder", coder_node)
    graph.add_node("reviewer", reviewer_node)
    graph.add_node("tester", tester_node)
    graph.add_node("next_task_router", next_task_router_node)

    # 2. 添加边
    # 入口 → Planner
    graph.set_entry_point("planner")

    # Planner → Coder（直线）
    graph.add_edge("planner", "coder")

    # Coder → 条件判断 → Reviewer 或跳过
    graph.add_conditional_edges("coder", after_coder, {
        "reviewer": "reviewer",
        "skip_to_end": "next_task_router",
    })

    # Reviewer → 条件判断 → Coder(回退) 或 Tester(通过)
    graph.add_conditional_edges("reviewer", after_reviewer, {
        "coder": "coder",
        "tester": "tester",
    })

    # Tester → 条件判断 → Coder(回退) 或 下一个任务
    graph.add_conditional_edges("tester", after_tester, {
        "coder": "coder",
        "next_or_end": "next_task_router",
    })

    # 下一个任务判断 → Coder 或 END
    graph.add_conditional_edges("next_task_router", next_task_or_end, {
        "coder": "coder",
        "end": END,
    })

    return graph


# ── 编译图（可运行的工作流）──

def compile_graph():
    """编译并返回可执行的 LangGraph 工作流。"""
    graph = build_graph()
    return graph.compile()
    
# ============================================================
# 快速验证
# ============================================================

if __name__ == "__main__":
    app = compile_graph()

    # 用最小输入跑一遍占位节点，验证图结构正确
    initial_state: AgentState = {
        "user_request": "写一个 hello world",
        "tasks": [],
        "current_task_index": 0,
        "retry_count": 0,
        "max_retries": 3,
        "file_changes": [],
        "review_report": {},
        "test_report": {},
    }

    result = app.invoke(initial_state)
    print("图结构验证通过！最终状态：")
    for k, v in result.items():
        print(f"  {k}: {v}")
