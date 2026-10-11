from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String, Text, DateTime, func, JSON, CheckConstraint, ForeignKey
from ..database import Base
from datetime import datetime

# ForeignKey 和 relationship 的区别是：
# ForeignKey 是在数据库层面上定义外键约束，会产生新的数据列
# relationship 是在 ORM 层面上定义对象之间的关系，相当于定义一个内存中的属性，不会产生新的数据列

class Task(Base):
    __tablename__ = "tasks"
    __table_args__ = (
        CheckConstraint('retry_count >= 0 AND retry_count <= 3'),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))  # 外键关联到 Project 模型
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=True)
    dependencies: Mapped[list|None] = mapped_column(JSON, nullable=True)  # 依赖任务的ID列表，存储为JSON字符串
    expected_output: Mapped[list|None] = mapped_column(JSON, nullable=True)  # 预期输出，存储为JSON字符串
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")  # 状态字段，默认值为 "pending"
    plan_result: Mapped[dict|None] = mapped_column(JSON, nullable=True)  # 计划结果，存储为JSON字符串
    review_report: Mapped[dict|None] = mapped_column(JSON, nullable=True)  # 审核报告，存储为JSON字符串
    test_report: Mapped[dict|None] = mapped_column(JSON, nullable=True)  # 测试报告，存储为JSON字符串
    retry_count: Mapped[int] = mapped_column(nullable=False, default=0)  # 重试次数，默认值为0
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())