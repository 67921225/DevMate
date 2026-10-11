from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String, Text, DateTime, func
from ..database import Base
from datetime import datetime


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(nullable=False, default=1)  # MVP阶段，默认值为1
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=True)
    workspace_path: Mapped[str] = mapped_column(String(512), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="idle")  # 状态字段，默认值为 "idle"
    # Mapped 中要使用 python 类型
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())