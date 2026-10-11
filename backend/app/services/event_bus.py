# 实现事件队列
import asyncio

# 事件总线类
class EventBus:
    def __init__(self):
        self._queues = {}
        self.loop = None

    # 前端调用，是存在事件循环的
    def subscribe(self, task_id) -> asyncio.Queue:
        """
        订阅事件队列
        :param task_id: 任务ID
        :return: asyncio.Queue对象
        """
        queue = asyncio.Queue()
        loop = asyncio.get_running_loop()
        # 将队列注册到事件总线中
        self.register(task_id, queue)
        self.loop = loop

        return queue

    def register(self, task_id, queue: asyncio.Queue):
        """
        注册事件队列
        :param task_id: 任务ID
        :param queue: asyncio.Queue对象
        """
        if task_id not in self._queues:
            self._queues[task_id] = []
        self._queues[task_id].append(queue)

    def unsubscribe(self, task_id, queue: asyncio.Queue):
        """
        取消订阅事件队列
        :param task_id: 任务ID
        :param queue: asyncio.Queue对象
        """
        if task_id in self._queues:
            self._queues[task_id].remove(queue)
            if not self._queues[task_id]: # 如果队列为空，则删除该任务ID的队列
                del self._queues[task_id]

    # 后端调用，是同步的，不存在事件循环
    def publish(self, task_id, event):
        """
        发布事件到指定任务ID的队列中
        :param task_id: 任务ID
        :param event: 事件对象
        """
        loop = self.loop
        if task_id in self._queues:
            for queue in self._queues[task_id]:
                loop.call_soon_threadsafe(queue.put_nowait, event)

event_bus = EventBus()