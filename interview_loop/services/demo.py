import re

DEMO_ANSWER = "这是演示模式下的示例回答。系统会继续模拟追问、阶段推进和复盘，不会调用真实模型或语音接口。"


def build_demo_llm_response(system_prompt: str, user_msg: str) -> str:
    if "JSON 数组" in user_msg:
        return '["RAG", "Temporal"]'
    if "面试评审" in system_prompt:
        return """## 演示复盘
- 评分：8/10
- 优点：结构清晰，能够结合真实项目说明技术取舍。
- 不足：部分回答可以进一步补充量化结果和失败案例。
- 建议：继续训练项目深挖、系统设计和故障排查。"""
    match = re.search(r"当前主问题：第 (\d+)/(\d+) 个：([^\n]+)", system_prompt)
    if match:
        number, total, topic = match.groups()
        return f"【演示题 {number}/{total}】请结合你的真实经历说明：{topic}"
    return "【演示题】请结合你的实际经历说明一个具体案例、关键取舍和最终结果。"
