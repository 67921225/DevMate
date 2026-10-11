from sqlalchemy.orm import Session
from sqlalchemy import select
from fastapi import APIRouter, Depends, HTTPException
from ..models.project import Project
from ..schemas.project import ProjectCreate, ProjectUpdate, ProjectResponse
from ..database import SessionLocal
from ..config import WORK_DIR
import os
import shutil

def get_db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()

# 路径边界检查函数
def is_valid_path(path: str) -> bool:
    abs_path = os.path.abspath(path)
    abs_work = os.path.abspath(WORK_DIR)
    return abs_path.startswith(abs_work + os.sep)

router = APIRouter()

@router.post("/projects", summary="创建新项目", response_model=ProjectResponse)
def add_data(request: ProjectCreate, db: Session = Depends(get_db)):
    path = os.path.join(WORK_DIR, request.name)
    
    # 创建一个新的项目实例
    new_project = Project(
        name = request.name,
        description = request.description,
        workspace_path = path,  # 假设 WORK_DIR 是一个全局配置的工作空间目录
    )

    # 项目名称校验，成功，创建文件夹
    if is_valid_path(path):
        os.makedirs(path, exist_ok=True)  # 如果文件夹已存在，则不会抛出异常 
    else:
        raise HTTPException(status_code=400, detail="Invalid project path")

    # 将新项目添加到数据库会话中
    db.add(new_project)
    db.commit()  # 提交事务，将数据写入数据库
    db.refresh(new_project)  # 刷新实例以获取数据库生成的字段（如ID）

    # BaseModel 自带的方法
    return ProjectResponse.model_validate(new_project)

@router.get('/projects', summary="获取所有项目", response_model=list[ProjectResponse])
def get_projects(db: Session = Depends(get_db)):

    # 1.x 的写法，也可以跑
    # projects = db.query(Project).all()

    projects = db.execute(select(Project)).scalars().all()  # 2.x 的写法
    return [ProjectResponse.model_validate(project) for project in projects]

@router.get('/projects/{project_id}', summary="根据ID获取项目", response_model=ProjectResponse)
def get_project_by_id(project_id: int, db: Session = Depends(get_db)):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return ProjectResponse.model_validate(project)

@router.put('/projects/{project_id}', summary="更新项目", response_model=ProjectResponse)
def update_project(project_id: int, request: ProjectUpdate, db: Session = Depends(get_db)):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    '''
    用于对资源进行部分更新。客户端通常只发送需要修改的字段。如果直接使用接收到的全部数据去更新数据库，
    未提供的字段可能会被错误地覆盖为 None 或默认值。
    '''
    update_project = request.model_dump(exclude_unset=True) # 返回值是一个字典
    for key, value in update_project.items():
        setattr(project, key, value)  # 使用 setattr 动态设置属性值

    db.commit()  # 提交事务，将更新写入数据库
    db.refresh(project)  # 刷新实例以获取最新数据

    return ProjectResponse.model_validate(project)

@router.delete('/projects/{project_id}', summary="删除项目")
def delete_project(project_id: int, db: Session = Depends(get_db)):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    db.delete(project)  # 删除项目

    if is_valid_path(project.workspace_path):
        try:
            shutil.rmtree(project.workspace_path, ignore_errors=True)
        except OSError as e:
            raise HTTPException(status_code=500, detail=f"Error deleting project directory: {e}")
        
    db.commit()  # 提交事务，将删除操作写入数据库

    return {"detail": f"Project {project_id} deleted successfully"}