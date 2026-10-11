import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # 项目根
from Agent.state import AgentState      # AgentState 在 state.py，不在 orchestration.py
from Agent.planner import planner_node
import json
import datetime

TASKS = [                          # ← 列表，5 个独立元素
    "写一个 utils.py 工具模块，包含 is_prime / fibonacci / gcd / lcm 四个函数，带类型注解和 docstring。",
    "写一个命令行待办事项应用，支持 add/list/done/delete 子命令，数据持久化到 todos.json —— CLI 应用。",
    "写一个脚本：生成 100 条随机访问日志写入 access.log，再统计每个 IP 的访问次数输出 Top 5 —— 自包含数据流。",
    "写一个 FastAPI 应用 main.py，提供 POST /items 和 GET /items/{item_id} 接口，内存字典存储 —— Web 服务。",
    "写一个图书管理系统：book.py 定义 Book 数据类，library.py 定义 Library 类（add/remove/borrow/return/search），cli.py 提供命令行交互 —— 多文件架构。",
]

def evaluate_one(request: str) -> dict:   # ← 测"一个"任务，返回一个结果 dict
    state = {
        "user_request": request, 
        "tasks": [], 
        }
    start = time.time()
    try:
        planner_node(state)
        return {
            "success": len(state["tasks"]) > 0,
            "num_subtasks": len(state["tasks"]),
            "subtask_titles": [t["title"] for t in state["tasks"]],
            "elapsed_sec": time.time() - start,
            "error": None,
        }
    except Exception as e:
        return {"success": False, "num_subtasks": 0,
                "subtask_titles": [], "elapsed_sec": 0, "error": str(e)}


if __name__ == "__main__":
    Base_file = os.path.dirname(os.path.abspath(__file__))
    result_route = os.path.join(Base_file, "results")
    os.makedirs(result_route, exist_ok=True)   # 创建目录（如果不存在）

    results = []
    for i, r in enumerate(TASKS, start=1):
        print(f"[{i}/{len(TASKS)}] 评估: {r[:32]}...")
        res = evaluate_one(r)
        print(f"  -> {'成功' if res['success'] else '失败'}，{res['num_subtasks']} 个子任务")
        results.append(res)

    # 汇总：成功率 = 成功数/总数，平均任务数，失败样本 id
    success_rate = sum(r["success"] for r in results) / len(results)
    avg_num_subtasks = sum(r["num_subtasks"] for r in results) / len(results)
    failed_samples = [i for i, r in enumerate(results) if not r["success"]]

    # json.dump 落盘（带时间戳 + model 名）
    with open(result_route + "/planner_eval_" + datetime.datetime.now().strftime('%Y%m%d%H%M%S') + ".json", "w", encoding='utf-8') as f:
        json.dump({
            "model": "deepseek-chat",
            "summary": {"success_rate": success_rate, "avg_num_subtasks": avg_num_subtasks, "failed_samples": failed_samples},
            "results": results,  # 每个任务的详细结果
        }, f, indent=4, ensure_ascii=False)
