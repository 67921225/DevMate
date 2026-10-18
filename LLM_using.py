# 实现 LLM 调用层
# 构建一个支持多模型的 Agent
# ABC 允许你定义一个不能被实例化的父类，并强制其子类必须实现某些指定方法，即抽象基类
from abc import ABC, abstractmethod
from openai import OpenAI 
import os, sys, time, random
# 用于转换 langchain_schema 格式
from pydantic import BaseModel
from openai import RateLimitError, InternalServerError, APIConnectionError, APITimeoutError


# Windows 控制台 UTF-8 支持
sys.stdout.reconfigure(encoding='utf-8')

class LLMProvider(ABC):
    @abstractmethod
    def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None, # 联合类型，表示这个参数也可以是 None
        tool_choice: str = "auto",
        temperature: float = 0,
        ):
        pass

    def chat_structured(self, messages: list[dict], output_model: type[BaseModel], temperature: float = 0) -> BaseModel:
        json_schemas = output_model.model_json_schema()
        tool = {
            'type': 'function',
            'function': {
            'name': 'structured_method',
            'description': 'Converts the input text to a structured format according to the provided JSON schema.',
            'parameters': json_schemas # 这个工具入参的结构
            }
        }
        results = self.chat(
            messages, 
            tools=[tool],
            tool_choice={
                'type': 'function',
                'function': {'name': 'structured_method'}
                }, 
            temperature=temperature,
            )

        if results['tool_calls'] is None:
            raise ValueError("模型未返回 tool_calls，结构化输出失败")
        
        return output_model.model_validate_json(results["tool_calls"][0]["function"]["arguments"])
        # results["tool_calls"] 返回调用的工具列表，取第一个工具
    
       
class DeepseekProvider(LLMProvider):
    # 实现 Deepseek 的 chat 方法
    def __init__(self, base_url: str = None, api_key: str = None, model: str = 'deepseek-chat'):
        self.client = OpenAI(
            base_url=base_url or os.getenv("DEEPSEEK_API_URL", "https://api.deepseek.com"),
            api_key=api_key or os.getenv("DEEPSEEK_API_KEY"),
        )
        self.model = model

    def chat(
        self,
        messages,
        tools = None,
        tool_choice = "auto",
        temperature = 0,
        )-> dict:

        # Implementation for Deepseek model
        # 添加重试机制，指数退避
        max_retries = 5
        for attempt in range(max_retries):
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    tools=tools,
                    tool_choice=tool_choice,
                    temperature=temperature,
                    stream=False,
                )

                # 只处理一次对话，多轮处理参看 loop
                msg = response.choices[0].message

                # 规范化格式
                tool_calls = None
                if msg.tool_calls:
                    tool_calls = [
                        {
                            'id': tc.id,
                            "type": 'function',
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments,
                            }
                        } 
                        for tc in msg.tool_calls
                    ]
                return {
                    "content": msg.content,
                    "tool_calls": tool_calls,
                }
            except (RateLimitError, InternalServerError, APIConnectionError, APITimeoutError) as e:
                # 可重试的错误：限流 / 服务器错误 / 网络抖动
                if attempt == max_retries - 1:
                    raise e              # 重试耗尽，原样抛给上层
                time.sleep(random.uniform(0, 2**attempt))      # 指数退避并使用 jitter 防止服务器集中请求