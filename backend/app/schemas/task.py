from pydantic import BaseModel, Field
from datetime import datetime

class TaskCreate(BaseModel):
    project_id: int
    # 使用 Field 拦截空字符串，但注意，不能拦截空格
    request: str = Field(min_length=1, description="任务请求内容")

class TaskResponse(BaseModel):
    # 返回所有字段
    model_config={"from_attributes": True}
    id: int
    project_id: int
    title: str
    description: str | None = None
    dependencies: list[int] | None = None  # 依赖任务的ID列表
    expected_output: list[str] | None = None  # 预期输出
    status: str
    plan_result: dict | None = None  # 计划结果
    review_report: dict | None = None  # 审核报告
    test_report: dict | None = None  # 测试报告
    retry_count: int
    created_at: datetime
    updated_at: datetime