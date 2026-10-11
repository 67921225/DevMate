from fastapi import FastAPI
from .database import engine, Base
from .routers import project, ws, task

app = FastAPI(title="DevMate")

# 启动时自动建表
Base.metadata.create_all(bind=engine)

# 注册路由
app.include_router(project.router)
app.include_router(ws.router)
app.include_router(task.router)