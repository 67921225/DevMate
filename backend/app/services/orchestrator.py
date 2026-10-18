import sys, os
from .event_bus import event_bus
from datetime import datetime
from ..config import BASE_DIR
from ..models.agent_log import AgentLog
from concurrent.futures import ThreadPoolExecutor
from .memory import add_experience, retrieve_experiences

path = os.path.dirname(BASE_DIR) # 取得父目录
sys.path.insert(0, path)
# 建立线程池限制并发数
executor = ThreadPoolExecutor(max_workers=6)

from Agent.orchestration import compile_graph
import tools

app = compile_graph()


def run_task(task_id, request, workspace_path):
    """
    启动一个后台线程
    """
    executor.submit(_worker, task_id, request, workspace_path)  # target 指定线程执行的函数

# —— 处理事件的函数 ——
def _handle_event(task_id, session, event):
    """处理节点事件，根据节点名称和当前状态执行相应的逻辑。"""
    event["created_at"] = datetime.now()
    event_bus.publish(task_id, event)
    # 将日志记录到数据库
    log_entry = AgentLog(
        task_id=task_id,
        agent_name=event["agent_name"],
        log_type=event["log_type"],
        content=event["content"],
        meta=event.get("metadata"),
        created_at=event["created_at"]  # 获取当前时间
    )
    session.add(log_entry)  # 将日志记录到数据库
    session.commit()

def _worker(task_id, request, workspace_path):
    """
    后台线程执行的函数
    """
    from ..database import SessionLocal
    from ..models import Task

    session = SessionLocal() 
    # 必须在线程中调用
    tools.set_workspace(workspace_path)
    tools.set_event_sink(lambda event: _handle_event(task_id, session, event))

    initial_state = {
        "user_request": request,
        "tasks": [],
        "current_task_index": 0,
        "retry_count": 0,
        "max_retries": 3,
        "file_changes": [],
        "review_report": {},
        "test_report": {}
    }
    # 任务执行

    task = session.get(Task, task_id)
    
    try:
        if task:
            task.status = "running"
            session.commit()
            
        plan_result = None
        final_test = None

        exps = retrieve_experiences(request, k=3)
        context_parts = []
        for e in exps:
            # ① 从 SQLite 查完整内容
            task = session.get(Task, e["task_id"])          
            if task and task.plan_result:                    
                titles = [t.get("title", "") for t in task.plan_result.get("tasks", [])]    
                steps = "；".join(f"{i+1}. {t}" for i, t in enumerate(titles))
                context_parts.append(f"- 类似需求「{e['description']}」曾拆成：{steps}")
            else:                                            
                context_parts.append(f"- 类似需求「{e['description']}」")
        context = "\n".join(context_parts)
        initial_state["context"] = context

        for step in app.stream(initial_state, stream_mode="updates"):
            for node_name, update in step.items():
                # node_name 是 "planner" / "coder" / ...
                if node_name == "planner":
                    plan_result = update["tasks"]
                if node_name == "tester":
                    final_test = update["test_report"]     
                event = {
                    "agent_name": node_name,
                    "log_type": "state_change",
                    "content": f"节点 {node_name} 已完成",
                }
                _handle_event(task_id, session, event) 
        # 任务完成标记
        if task:
            task.plan_result = {"tasks": plan_result}       
            task.test_report = final_test     
            task.status = "done"
            session.commit()

        try:
           add_experience(task_id, request)
        except Exception as e:
           print(f"记忆写入失败（不影响任务结果）: {e}")

        task_complete_event = {
            "agent_name": "orchestrator",
            "log_type": "task_complete",
            "content": "任务已完成",
        }
        _handle_event(task_id, session, task_complete_event)

    except Exception as e:
        if task:
            task.status = "failed"
            session.commit()
        # 记录异常日志
        error_event = {
            "agent_name": "orchestrator",
            "log_type": "task_failed",
            "content": f"任务执行异常: {str(e)}",
        }
        _handle_event(task_id, session, error_event)  
        print(f"任务 {task_id} 执行异常: {str(e)}")  # 打印异常信息

    finally:
        session.close()