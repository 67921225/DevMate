import logging

from Agent.state import AgentState
from Agent.Agentloop import agent_loop
from tools import read_file
from settings import settings, timeit

logger = logging.getLogger(__name__)

system_prompt = """
    你是一个专业的程序员，能够编写高质量的代码。
    要求：
    1、根据用户请求，生成高质量的代码。
    2、代码要能满足用户需求。
    3、代码要符合编程规范。
    4、代码要做好注释。
    5、新建文件使用 write_file 工具，将生成的代码写入文件; 不要只在回复里展示代码内容。
    6、如果只需要修改一部分，则优先使用 edit_file 工具，将修改部分写入文件。注意：
       1、old_string 要和文件原文逐字符一致（含缩进和换行），new_string 是你要写进去的新内容。。
       2、找不到或报错时，使用 read_file 工具，重新读取文件内容。
       3、"old_string 要足够长、带上前后上下文，确保它能在文件里唯一定位到你要改的那一处"。
    """

@timeit
def coder_node(state: AgentState) -> AgentState:
    """
    Coder Agent 节点 —— 基于 agent_loop 执行编码任务。

    读取: state["tasks"], state["current_task_index"]
    产出: state["file_changes"]
    """
    tasks = state["tasks"]

    current_task_index = state["current_task_index"]

    current_task = tasks[current_task_index]
    # 获取当前任务的信息
    current_task_dependencies = current_task.get("dependencies") or []     # list[int]
    current_task_expected_output = current_task.get("expected_output") or []     # list[str]

    dep_files = []
    for t in tasks:
        if t["id"] in current_task_dependencies:
           dep_files.extend(t["expected_output"])

    context_parts = []
    for f in dep_files:
        content = read_file.func(f)               # 不存在会返回"错误:..."，不会崩
        context_parts.append(f"--- {f} ---\n{content}")

    # loop 的输入是 str
    user_input = [f"编码任务：{current_task['description']}\n你要产出的文件：{current_task_expected_output}"]
    if context_parts:
        user_input.append("[前置任务已产出的文件]\n" + "\n".join(context_parts))

    # 考虑重试
    if state["retry_count"] > 0:
        feedback_lines = []
        review = state.get("review_report", {})
        test = state.get("test_report", {})
        if review:
            feedback_lines.append(f"审查反馈：{review}")
        if test:
            feedback_lines.append(f"测试反馈：{test}")
        if feedback_lines:
            user_input.append("上一轮未通过，请修复：\n" + "\n".join(feedback_lines))

    prompt = "\n".join(user_input)

    res = agent_loop(system_prompt, prompt, max_steps=settings.max_steps, agent_name="coder")

    state["file_changes"].extend(res['file_path'])

    return state
