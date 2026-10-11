from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .database import engine, Base
from .routers import project, ws, task

app = FastAPI(title="DevMate")

# 启动时自动建表
Base.metadata.create_all(bind=engine)

# 注册路由
app.include_router(project.router)
app.include_router(ws.router)
app.include_router(task.router)

# 托管前端静态文件
# 为什么放在所有 API 路由之后：mount("/") 会兜底匹配所有未被前面路由
# 处理的路径，若放在 include_router 之前，会拦截 /projects、/tasks 等接口。
# 为什么 parent 连取三级：main.py 位于 backend/app/ 下，往上三级才是项目
# 根目录，frontend/ 目录就在根目录下。
app.mount(
    "/",
    StaticFiles(directory=str(Path(__file__).parent.parent.parent / "frontend"), html=True),
    name="frontend",
)