"""
L3 端到端评估：跑完整 pipeline（Planner → Coder → Reviewer → Tester → 回退），
统计 done 率 + 测试通过率 + 平均耗时。

与 planner_eval 的区别：
- 这里跑完整图（会真实写文件、跑 pytest、调 LLM，产生费用）。
- 每个任务独立 workspace（eval/workspaces/task_i），互不污染。

指标说明：
- done_rate：invoke 正常结束（未抛异常）的比例。
- test_pass_rate：以"子任务"为粒度，累加每个子任务最后一次 tester 报告的
  通过数/失败数后计算 passed/(passed+failed)。这样"前面子任务全过、最后一个
  失败"不再被整题记成 0 分。
- 未被 tester 覆盖的子任务（如 Reviewer 连续驳回、未进入测试即放弃）不产生
  测试数据，不计入 passed/failed。
"""

import sys, os, time, json, datetime

# Windows 控制台 UTF-8
sys.stdout.reconfigure(encoding='utf-8')

# 项目根加入 sys.path（eval/ 的上一级）
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from Agent.orchestration import compile_graph
from tools import set_workspace

# 精简到 3 个任务（端到端每个任务 ~10+ 次 LLM 调用，控制成本）
TASKS = [
    "写一个 utils.py 工具模块，包含 is_prime / fibonacci / gcd / lcm 四个函数，带类型注解和 docstring。",
    "写一个命令行待办事项应用，支持 add/list/done/delete 子命令，数据持久化到 todos.json。",
    "写一个 FastAPI 应用 main.py，提供 POST /items 和 GET /items/{item_id} 接口，内存字典存储。",
]

app = compile_graph()


def evaluate_one(request: str, workspace_dir: str) -> dict:
    """对单个需求跑完整 pipeline，返回结果 dict。"""
    os.makedirs(workspace_dir, exist_ok=True)
    set_workspace(workspace_dir)  # 每个任务独立 workspace，互不污染

    initial_state = {
        "user_request": request,
        "tasks": [],
        "current_task_index": 0,
        "retry_count": 0,
        "max_retries": 3,
        "file_changes": [],
        "review_report": {},
        "test_report": {},
    }

    start = time.time()
    try:
        # 用 stream 捕获每个节点的更新，而不是 invoke 的最终 state。
        # 原因：next_task_router 在每个子任务结束后都会重置 test_report，
        # 导致 invoke 的最终 state 里 test_report 恒为空。
        #
        # 为什么从"只取最后一个子任务"改成"累加所有子任务"：
        # 一个任务常被 planner 拆成多个子任务，每个子任务的 tester 都产出一次
        # test_report。旧逻辑只保留最后一次（final_test），于是"前面子任务全过、
        # 最后一个失败"时整题被记 0 分，avg_test_pass_rate 严重失真。新逻辑以
        # next_task_router 作为"子任务结束"的边界：在边界处把当前子任务最后一次
        # tester 结果累加进总数，既覆盖所有子任务，又不会把同子任务重试的中间
        # 失败重复计数。
        num_subtasks = 0
        total_passed = 0
        total_failed = 0
        current_test = None  # 当前子任务最近一次 tester 的 test_report

        for step in app.stream(initial_state, stream_mode="updates"):
            for node_name, update in step.items():
                if node_name == "planner" and "tasks" in update:
                    num_subtasks = len(update.get("tasks", []))
                if node_name == "tester" and "test_report" in update:
                    # 同一子任务重试时 tester 会多次更新，这里只暂存最新的，
                    # 到子任务结束边界（next_task_router）才真正累加。
                    current_test = update.get("test_report")
                if node_name == "next_task_router":
                    # 子任务结束：把该子任务的最终测试结果累加进总数。
                    if current_test is not None:
                        total_passed += current_test.get("passed", 0)
                        total_failed += current_test.get("failed", 0)
                    current_test = None  # 重置，准备下一个子任务

        total = total_passed + total_failed
        return {
            "success": True,
            "elapsed_sec": round(time.time() - start, 1),
            "num_subtasks": num_subtasks,
            "passed": total_passed,
            "failed": total_failed,
            "test_pass_rate": round(total_passed / total, 3) if total else None,
            "error": None,
        }
    except Exception as e:
        return {
            "success": False,
            "elapsed_sec": round(time.time() - start, 1),
            "num_subtasks": 0,
            "passed": 0,
            "failed": 0,
            "test_pass_rate": None,
            "error": str(e),
        }


if __name__ == "__main__":
    base = os.path.dirname(os.path.abspath(__file__))
    ws_root = os.path.join(base, "workspaces")
    result_route = os.path.join(base, "results")
    os.makedirs(ws_root, exist_ok=True)
    os.makedirs(result_route, exist_ok=True)

    results = []
    for i, req in enumerate(TASKS, start=1):
        ws_dir = os.path.join(ws_root, f"task_{i}")
        print(f"[{i}/{len(TASKS)}] 评估: {req[:36]}...")
        res = evaluate_one(req, ws_dir)
        status = "done" if res["success"] else "FAILED"
        print(f"  -> {status} | {res['num_subtasks']} 子任务 | "
              f"passed={res['passed']} failed={res['failed']} | {res['elapsed_sec']}s")
        if res["error"]:
            print(f"     异常: {res['error'][:200]}")
        results.append(res)

    # 汇总
    n = len(results)
    done = sum(r["success"] for r in results)
    rates = [r["test_pass_rate"] for r in results if r["test_pass_rate"] is not None]
    summary = {
        "model": "deepseek-chat",
        "temperature": 0,
        "done_rate": round(done / n, 3),
        "avg_test_pass_rate": round(sum(rates) / len(rates), 3) if rates else None,
        "avg_elapsed_sec": round(sum(r["elapsed_sec"] for r in results) / n, 1),
    }

    out_path = os.path.join(result_route, "e2e_" + datetime.datetime.now().strftime("%Y%m%d%H%M%S") + ".json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"summary": summary, "results": results}, f, indent=4, ensure_ascii=False)

    print("\n=== 汇总 ===")
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    print(f"\n结果已落盘: {out_path}")
    print(f"workspace 产物保留在: {ws_root}（可查看 coder 写出的代码和测试）")
