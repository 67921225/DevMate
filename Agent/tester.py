"""
第4步：Tester Agent 节点
读取 Coder 产出的代码文件，自动生成 pytest 测试用例、运行测试、输出报告。
"""

import logging

from Agent.state import AgentState
from tools import read_file, execute_shell_command
import re
from Agent.Agentloop import agent_loop
from settings import settings, timeit

logger = logging.getLogger(__name__)

# ============================================================
# Tester Node
# ============================================================

@timeit
def tester_node(state: AgentState) -> AgentState:
    """
    Tester Agent 节点。

    读取: state["tasks"], state["current_task_index"], state["file_changes"]
    产出: state["test_report"]

    执行流程:
        1. 读取 Coder 修改的文件内容
        2. 调用 LLM 生成 pytest 测试代码
        3. 将测试代码写入文件
        4. 运行 pytest
        5. 解析测试结果，写入 test_report
    """
    # ── 1. 获取当前任务信息 ──
    current_task = state["tasks"][state["current_task_index"]]
    task_description = current_task.get("description", "无任务描述")
    file_changes = state["file_changes"]

    if not file_changes:
        # Coder 本轮没有产出任何文件，视为失败而不是"跳过"。
        # 为什么设 failed=1 并累加 retry_count：下游 after_tester 改成
        # "passed > 0 才放行"后，若这里仍返回 failed=0，会被路由回 Coder 重试，
        # 但重试次数不增加就永远到不了 max_retries，会死循环。设 failed=1 并
        # 累加重试次数，才能让"没产出文件"像普通失败一样走完 重试→放弃 流程。
        state["test_report"] = {
            "passed": 0,
            "failed": 1,
            "failures": ["Coder 未产出任何文件"],
            "summary": "没有文件变更，视为失败"
        }
        state['retry_count'] = state.get('retry_count', 0) + 1
        return state

    # ── 2. 读取修改的文件内容 ──
    file_contents = []
    for file_path in file_changes:
        content = read_file.func(file_path)
        # 如果文件不存在（如 Agent 声称写入但实际未写入），跳过
        if content.startswith("错误:"):
            file_contents.append(f"--- {file_path} ---\n[文件读取失败: {content}]")
        else:
            file_contents.append(f"--- {file_path} ---\n{content}")

    # ── 3. 调用 LLM 生成测试代码 ──
    system_prompt = """
            你是一个资深测试工程师。你需要为给定的 Python 代码编写 pytest 测试用例.
            要求：
            1. 覆盖所有函数/API 端点的正常和异常情况
            2. 使用 pytest 框架
            3. Mock 外部依赖（数据库、第三方 API 等）
            4. 测试用例命名清晰，建议包含 given/when/then 注释
            5. 测试代码必须完整、可直接运行
            6. 如果代码是 FastAPI 应用，使用 TestClient 或 httpx.AsyncClient 测试
            7. 使用 write_file 工具把测试代码写入文件（文件名以 test_ 开头），不要只在回复里展示代码
            8. 读被测代码时按需分块，不要读整个大文件：先 search_code 定位函数/类，再用 read_file 的 start_line/end_line 只读需要的行区间
            """
    
    user_request = f"""
        任务描述：{task_description}
        以下是要测试的代码文件：
        {chr(10).join(file_contents)}
        请为以上代码生成 pytest 测试用例。
        """
    response = agent_loop(system_prompt, user_request, max_steps=settings.max_steps, agent_name="tester")  # 调用 AgentLoop 进行对话

    # ── 4. 获取 agent_loop 返回结果
    # 但是因为有两条分支，要检查是否报错
    if "error" in response:
        state["test_report"] = {
            "passed": 0,
            "failed": 1,
            "failures": [{"error": response["error"]}],
            "summary": "Tester: LLM 返回错误信息"
        }
        state['retry_count'] = state.get('retry_count', 0) + 1
        return state
    
    # 正常返回
    content = response["result"]
    file_path = response["file_path"]

    if not content:
        state["test_report"] = {
            "passed": 0,
            "failed": 1,
            "failures": [{"error": "LLM 返回内容为空"}],
            "summary": "Tester: LLM 未返回任何内容"
        }
        state['retry_count'] = state.get('retry_count', 0) + 1
        return state

    # 测试文件路径
    if not file_path:
        state["test_report"] = {
            "passed": 0,
            "failed": 1,
            "failures": [{"error": "LLM 返回内容中未包含测试文件路径"}],
            "summary": "Tester: LLM 未返回测试文件路径"
        }
        state['retry_count'] = state.get('retry_count', 0) + 1
        return state

    # ── 6. 运行 pytest ──
    test_files = " ".join(file_path)
    result = execute_shell_command.func(f"python -m pytest {test_files} -v --tb=short")

    # ── 7. 解析测试结果 ──
    # pytest 成功时 stdout 包含 "X passed"，失败时错误信息包含结果摘要
    passed = 0
    failed = 0
    
    failures = []

    failure_lines = []
    for line in result.split("\n"):
        if "FAIL" in line or "AssertionError" in line or "assert" in line.lower():
            failure_lines.append(line.strip())
    failures = failure_lines[:10]  # 最多保留 10 条

    passed_match = re.search(r"(\d+)\s*passed", result)
    failed_match = re.search(r"(\d+)\s*failed", result)
    
    if passed_match:
        passed = int(passed_match.group(1))
    if failed_match:
        failed = int(failed_match.group(1))

    # 为什么加这段：pytest 一个测试都没收集到时（如测试代码没落盘、或收集阶段
    # 报错），输出里没有 "X passed / Y failed" 字样，上面两个正则都匹配不到，
    # 只能得到 passed=0、failed=0。但"0 个测试运行"和"全部通过"是两回事：
    # 前者是根本没测到东西，绝不能当成成功，否则 orchestration 的 after_tester
    # 会把"没测到任何测试"误判成"全部通过"，让流水线带着假成功结束。
    if passed == 0 and failed == 0:
        failed = 1
        failures.append("未真正运行任何测试：pytest 未收集到测试或执行报错")

    # ── 8. 写入 state ──
    state["test_report"] = {
        "passed": passed,
        "failed": failed,
        "failures": failures,
        "summary": f"测试完成: {passed} 通过, {failed} 失败"
    }
    if failed > 0:
        state['retry_count'] = state.get('retry_count', 0) + 1
    logger.info(f"Tester 报告: {state['test_report']['summary']}")
    return state
