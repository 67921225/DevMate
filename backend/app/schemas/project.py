from pydantic import BaseModel
from datetime import datetime

class ProjectCreate(BaseModel):
    name: str
    description: str | None = None

class ProjectUpdate(BaseModel):
    name: str | None = None
    description: str | None = None

class ProjectResponse(BaseModel):
    # 返回所有字段
    model_config={"from_attributes": True}
    id: int 
    user_id: int  
    name: str  
    description: str | None = None
    workspace_path: str  
    status: str  
    created_at: datetime  
    updated_at: datetime  
    