from Agent.state import AgentState
from LLM_using import DeepseekProvider
from Agent.schemas import TaskPlan

SystemPrompt = '''
    你是一个架构师，你的任务是接受用户的输入，并将用户的需求划分成子任务。
    注意合理划分任务数量。
'''

LLM = DeepseekProvider()

def planner_node(state: AgentState) -> AgentState:

    user_request = state["user_request"]
    context = state.get("context", "")  # 获取上下文信息，如果不存在则使用空字符串
    user_prompt = user_request 

    if context:
       user_prompt = f"{user_request}\n\n[历史类似任务经验]\n{context}"

    messages = [
        {"role": "system", "content": SystemPrompt},
        {"role": "user", "content": user_prompt}
    ]

    try:
        plan = LLM.chat_structured(messages, TaskPlan)
        state["tasks"] = [t.model_dump() for t in plan.tasks]
    except Exception as e:
        print(f"Planner 降级: {e}")
        state["tasks"] = []
        return state
    
    return state