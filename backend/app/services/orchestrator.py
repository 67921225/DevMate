import sys, os
import threading
from .event_bus import event_bus
from datetime import datetime
from ..config import BASE_DIR
from ..models.agent_log import AgentLog

path = os.path.dirname(BASE_DIR) # 取得父目录
sys.path.insert(0, path)

from Agent.orchestration import compile_graph
import tools

app = compile_graph()


def run_task(task_id, request, workspace_path):
    """
    启动一个后台线程
    """
    thread = threading.Thread(target=_worker,args=(task_id, request, workspace_path), daemon=True)  # target 指定线程执行的函数
    thread.start()

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
        for step in app.stream(initial_state, stream_mode="updates"):
            for node_name in step:
                      # node_name 是 "planner" / "coder" / ...
                event = {
                    "agent_name": node_name,
                    "log_type": "state_change",
                    "content": f"节点 {node_name} 已完成",
                }
                _handle_event(task_id, session, event) 
        # 任务完成标记
        if task:
            task.status = "done"
            session.commit()

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