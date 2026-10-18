# 编写3个 pydantic 模型，这一步的目的是结构化输出
# Pydantic 模型主要是定义接口的数据类型，便于数据校验
# 在 FastAPI 里常见模式是：Pydantic 做 Schema，SQLAlchemy 做数据库表模型。
from typing import Literal
from pydantic import BaseModel

class TaskItem(BaseModel):
    id: int
    title: str
    description: str
    expected_output: list[str]
    dependencies: list[int] = []  # 当前任务依赖哪些前置任务

class TaskPlan(BaseModel):
    tasks: list[TaskItem]

class Issue(BaseModel):
    severity: Literal['critical', 'warning', 'suggestion']   # 对应策划书的 🔴🟡🟢
    file: str                                                # 哪个文件
    line: int | None = None                                  # 第几行（有的 issue 不定位到行）
    category: Literal['correctness', 'security', 'performance', 'quality', 'error_handling']
    title: str                                               # 一句话标题
    suggestion: str                                          # 修复建议

class ReviewReport(BaseModel):
    verdict: Literal['pass', 'fail']
    issues: list[Issue]
    summary: str