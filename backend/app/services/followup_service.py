"""上下文追问快路径。"""

from __future__ import annotations

FOLLOWUP_QUERY_MARKERS = (
    "怎么回事",
    "为什么",
    "啥意思",
    "什么意思",
    "受限",
    "看不到",
    "不能看",
)

SALARY_CONTEXT_MARKERS = (
    "薪酬",
    "总包",
    "基本工资",
    "奖金",
    "津贴",
    "个税",
    "社保",
    "受限",
)


def answer_contextual_followup(query: str, recent_assistant_content: str) -> str | None:
    """基于上一轮助手内容回答短追问，避免误走 chitchat 大模型。"""
    normalized_query = query.strip().lower()
    if not normalized_query:
        return None
    if not any(marker in normalized_query for marker in FOLLOWUP_QUERY_MARKERS):
        return None
    if not any(marker in recent_assistant_content for marker in SALARY_CONTEXT_MARKERS):
        return None
    if "受限" not in normalized_query and "受限" not in recent_assistant_content:
        return None
    return (
        "“受限”表示这些薪酬明细按当前账号权限做了脱敏处理。"
        "普通员工通常只能直接查看自己的薪酬总包，基本工资、奖金、津贴、个税、社保等拆分项会暂时隐藏；"
        "经理或 HR 角色会按权限看到更多明细。"
    )
