from fastapi import APIRouter, Depends, HTTPException
from ..schemas.task import TaskCreate, TaskResponse
from ..database import SessionLocal
from ..models.project import Project
from ..models.task import Task
from sqlalchemy.orm import Session
from ..services.orchestrator import run_task

router = APIRouter()

def get_db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()

# 建立任务，触发编排器
@router.post("/tasks", summary="创建新任务", response_model=TaskResponse)
def start_task(request: TaskCreate, db: Session = Depends(get_db)):
    project = db.get(Project, request.project_id)
    # 检查项目是否存在
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    # 建立 task 行
    task = Task(
        project_id = request.project_id,
        title = request.request[:50],
        description = request.request,
        status = 'pending'
    )
    db.add(task)
    db.commit()
    db.refresh(task)

    run_task(task.id, request.request, project.workspace_path)
    return TaskResponse.model_validate(task)
    
@router.get('/tasks/{task_id}', summary="根据ID获取子任务", response_model=TaskResponse)
def get_task_by_id(task_id: int, db: Session = Depends(get_db)):
    task = db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return TaskResponse.model_validate(task)
