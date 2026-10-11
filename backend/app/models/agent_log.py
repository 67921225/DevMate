from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String, Text, DateTime, func, JSON, ForeignKey
from ..database import Base
from datetime import datetime

class AgentLog(Base):
    __tablename__ = "agent_logs"
   
    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"))  # 外键关联到 task 模型
    agent_name: Mapped[str] = mapped_column(String(32), nullable=False)
    log_type: Mapped[str] = mapped_column(String(32), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=True)  # 日志内容
    meta: Mapped[dict|None] = mapped_column('metadata', JSON, nullable=True)  # 额外信息
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())