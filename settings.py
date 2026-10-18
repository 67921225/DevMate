"""集中管理运行参数（pydantic-settings）。

用法：
    from settings import settings
    settings.max_retries

与 backend/app/config.py 的分工：
    - config.py 管路径 / 数据库连接（静态）
    - settings.py 管可调运行参数 + 密钥（有默认值，可被 .env 覆盖）

放项目根目录的原因：Agent/（引擎层）和 backend/app/（后端层）都要访问。
"""
import logging
import time
from functools import wraps
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# 统一日志格式（所有模块共用，basicConfig 只在第一次生效）
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)


def timeit(func):
    """计时装饰器：自动记录函数耗时（INFO 级）"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        start = time.perf_counter()
        result = func(*args, **kwargs)
        elapsed = time.perf_counter() - start
        logging.getLogger(func.__module__).info(f"{func.__name__} 耗时 {elapsed:.3f}s")
        return result
    return wrapper


class Settings(BaseSettings):
    # ── LLM ──
    deepseek_api_key: str = ""
    deepseek_api_url: str = "https://api.deepseek.com"
    llm_max_retries: int = 5    # LLM 调用失败时的重试次数

    # ── Agent 编排 ──
    max_retries: int = 3        # 每个子任务最多回退重试次数
    max_steps: int = 10         # agent_loop 单次循环最大步数

    # ── 并发 ──
    max_workers: int = 6        # 线程池最大并发任务数

    # ── 经验记忆 ──
    retrieve_k: int = 3         # 新任务检索注入的历史经验条数
    memory_days: int = 30       # 记忆保留天数（过期自动清理）

    model_config = SettingsConfigDict(
        env_file=Path(__file__).parent / ".env",
        env_file_encoding="utf-8",
        extra="ignore",         # 忽略 .env 里不属于 Settings 的 key（避免误报）
    )


settings = Settings()
