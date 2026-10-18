import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from ..services.event_bus import event_bus
from fastapi.encoders import jsonable_encoder

logger = logging.getLogger(__name__)

router = APIRouter()

@router.websocket("/ws/tasks/{task_id}")
async def websocket_endpoint(websocket: WebSocket, task_id: int):
    """
    建立握手，并订阅事件队列
    :param websocket: WebSocket对象 
    :param task_id: 任务ID
    """
    await websocket.accept()
    queue = event_bus.subscribe(task_id)
    try:
        while True:
            event = jsonable_encoder(await queue.get())
            await websocket.send_json(event)
            # 使用 jsonable_encoder
            # 遇到 datetime → 转成 isoformat 字符串（"2026-08-23T12:00:00"）
            # 遇到 Pydantic 模型 → 转成普通 dict
            # 遇到 set、Enum 等 → 也各有对应转换
    except WebSocketDisconnect:
        # 记录
        logger.info(f"WebSocket disconnected for task_id: {task_id}")
    finally:
        event_bus.unsubscribe(task_id, queue)
    
        