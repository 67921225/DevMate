from Agent.state import AgentState
from tools import read_file, execute_shell_command
from LLM_using import DeepseekProvider
from Agent.schemas import ReviewReport

LLM = DeepseekProvider()

def reviewer_node(state: AgentState) -> AgentState:

    current_task_description = state['tasks'][state['current_task_index']]['description']

    file_changes = state['file_changes']

    prompt = f"""任务需求：{current_task_description}
    文件变化：{file_changes}
    请提供详细的审查报告，包括代码的优缺点、改进点和建议。注意：
    1、ruff 输出仅仅作为客观参考，而不是最终结论
    2、verdict 由LLM 综合"任务需求 + 代码 + lint 结果"判断
    """

    file_contents = []  # 读取所有文件内容
    lint_reports = []  # 保存所有文件的审查报告
    for file_path in file_changes:
        # 静态代码检查
        check_out = execute_shell_command.func(f"ruff check {file_path}") 
        if "未找到" not in check_out:  # 如果没有安装 ruff
            lint_reports.append(f"--- ruff {file_path} ---\n{check_out}")
        content = read_file.func(file_path)
        file_contents.append(f"--- {file_path} ---\n{content}")

    prompt += "\n" + "\n".join(file_contents)
    if lint_reports:
        prompt += "\n\n--- ruff 静态检查 ---\n" + "\n".join(lint_reports)

    messages = [
        {"role": "system", "content": "你是一个代码审查专家。请审查以下代码是否满足任务需求"},
        {"role": "user", "content": prompt}
    ]

    try:
        response = LLM.chat_structured(messages, ReviewReport)
        state['review_report'] = response.model_dump()
        if response.verdict == 'fail':
            state['retry_count'] += 1
        return state
    except Exception as e:
        print(f"Reviewer 降级: {e}")
        state["review_report"] = {
            'verdict': 'fail',
            'issues': [],
            'summary': '代码审查失败。'
        }
        state['retry_count'] += 1
        return state