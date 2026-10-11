# 实现一个 AgentLoop
import json

from LLM_using import DeepseekProvider
from langchain_core.utils.function_calling import convert_to_openai_tool

import tools

# ── 初始化 LLM ──
llm = DeepseekProvider()

# ── 工具注册（工具名 → Python 函数）──
TOOL_MAP = {
    "read_file":            tools.read_file,
    "write_file":           tools.write_file,
    "execute_shell_command": tools.execute_shell_command,
    "list_directory":       tools.list_directory,
    "search_code":          tools.search_code,
    "install_pkg":          tools.install_pkg,
    "edit_file":           tools.edit_file
}

# ── 工具 Schema（OpenAI 格式，传给 LLM）──
TOOL_SCHEMAS = [convert_to_openai_tool(fn) for fn in TOOL_MAP.values()]

def execute_tool(tool_call: dict) -> str:
    tool_name = tool_call["function"]["name"]
    tool_args = json.loads(tool_call["function"]["arguments"])
    func = TOOL_MAP.get(tool_name)
    if func is None:
        return f"错误: 未知工具 '{tool_name}'，可用工具: {list(TOOL_MAP.keys())}"

    try:
        # 执行工具函数，并返回结果, 使用 .func 消除装饰器的影响
        result = func.func(**tool_args)  
        return str(result)
    except Exception as e:
        return f"错误: 工具 '{tool_name}' 执行异常 —— {e}"

def agent_loop(system_prompt: str, user_request: str, max_steps: int = 20, agent_name: str = "Agent") -> dict:
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_request}
    ]

    # 用于记录修改的文件路径
    file_path = []
    # 循环前读一次 sink
    sink = tools.get_event_sink()

    for _ in range(max_steps):
        response = llm.chat(messages, tools=TOOL_SCHEMAS)
    
        # 事件一：记录 Agent 的思考过程（在前端展示）
        if sink and response["content"]:
            sink({
                "agent_name": agent_name, 
                "log_type": "thinking", 
                "content": response["content"],
                "metadata": {}
                })

        if response["tool_calls"] is None:
            # Agent 认为任务完成，返回结果
            return {
                'result': response["content"],
                'file_path': file_path
                }

        messages.append({
            "role": "assistant",
            "content": response["content"],
            "tool_calls": response["tool_calls"]
        })

        # 执行工具调用
        for tool_call in response["tool_calls"]:
            args = json.loads(tool_call["function"]["arguments"])
            # 事件二：记录 Agent 的工具调用过程
            if sink:
                sink({
                    "agent_name": agent_name, 
                    "log_type": "tool_call",
                    "content": tool_call["function"]["name"],
                    "metadata": {
                        "args": args,
                    }})
      
            # 执行工具调用
            result = execute_tool(tool_call)
            tool_name = tool_call["function"]["name"]
            # read_file 不截断；其余超长则首尾保留
            if tool_name != "read_file" and len(result) > 8000:
               result_for_llm = result[:2000] + f"\n...(中间省略 {len(result)-2*2000} 字符)...\n" + result[-2000:]
            else:
               result_for_llm = result

            # 事件三：记录 Agent 的工具调用过程
            content = result if len(result) <= 2000 else result[:2000] + "...(截断)"
            if sink:
                sink({
                    "agent_name": agent_name, 
                    "log_type": "tool_result",
                    "content": content,
                    "metadata": {"tool": tool_call["function"]["name"]}
                    })
       
            # 判断是不是 写文件， 如果是，将路径进行保存
            if tool_call["function"]["name"] == "write_file":
                file_path.append(args["path"])

            messages.append({
                "role": "tool",
                "tool_call_id": tool_call["id"],
                "content": result_for_llm
            })

    return {
        "error": "超过最大步数",
        "file_path": file_path
        }