"""项目内置样例数据。"""

from __future__ import annotations

EMPLOYEES: list[dict[str, object]] = [
    {
        "user_id": "u-1001",
        "username": "li.wei",
        "password": "RuiRui123!",
        "name": "李伟",
        "role": "employee",
        "department": "Finance",
        "manager_id": "u-2001",
        "phone": "13812345678",
        "id_card": "110101199001011234",
        "annual_leave": 7,
        "contract_end": "2027-12-31",
    },
    {
        "user_id": "u-1002",
        "username": "zhao.qin",
        "password": "RuiRui123!",
        "name": "赵琴",
        "role": "employee",
        "department": "HR",
        "manager_id": "u-3001",
        "phone": "13987654321",
        "id_card": "310101199206123456",
        "annual_leave": 10,
        "contract_end": "2028-06-30",
    },
    {
        "user_id": "u-2001",
        "username": "zhang.min",
        "password": "RuiRui123!",
        "name": "张敏",
        "role": "manager",
        "department": "Finance",
        "manager_id": "u-3001",
        "phone": "13711112222",
        "id_card": "320101198705051234",
        "annual_leave": 12,
        "contract_end": "2029-03-31",
    },
    {
        "user_id": "u-3001",
        "username": "wang.hr",
        "password": "RuiRui123!",
        "name": "王静",
        "role": "hr_admin",
        "department": "HR",
        "manager_id": None,
        "phone": "13622223333",
        "id_card": "440101198403102222",
        "annual_leave": 15,
        "contract_end": "2030-12-31",
    },
    {
        "user_id": "u-4001",
        "username": "chen.kb",
        "password": "RuiRui123!",
        "name": "陈楠",
        "role": "knowledge_admin",
        "department": "IT",
        "manager_id": None,
        "phone": "13566667777",
        "id_card": "510101199305063333",
        "annual_leave": 8,
        "contract_end": "2027-09-30",
    },
]

PAYROLL_RECORDS: list[dict[str, object]] = [
    {
        "record_id": "pay-2026-04-u1001",
        "user_id": "u-1001",
        "payroll_month": "2026-04",
        "base_salary": 18000,
        "bonus": 4000,
        "allowance": 1200,
        "tax": 2600,
        "social_security": 900,
        "total_package": 23200,
    },
    {
        "record_id": "pay-2026-04-u1002",
        "user_id": "u-1002",
        "payroll_month": "2026-04",
        "base_salary": 16500,
        "bonus": 3500,
        "allowance": 1000,
        "tax": 2300,
        "social_security": 880,
        "total_package": 21000,
    },
    {
        "record_id": "pay-2026-04-u2001",
        "user_id": "u-2001",
        "payroll_month": "2026-04",
        "base_salary": 26000,
        "bonus": 6800,
        "allowance": 1800,
        "tax": 5200,
        "social_security": 1400,
        "total_package": 34600,
    },
]

SEED_DOCUMENTS: list[dict[str, str]] = [
    {
        "filename": "差旅报销制度.txt",
        "department": "Finance",
        "content": (
            "差旅报销制度：国内出差优先选择经济舱，高铁优先二等座。"
            "如行程超过两小时且涉及重要客户接待，可申请商务舱或一等座。"
            "住宿标准：一线城市每晚不超过800元，其他城市每晚不超过500元。"
            "出租车需附电子发票，餐补标准为每人每天120元。"
        ),
    },
    {
        "filename": "员工年假与合同规则.txt",
        "department": "HR",
        "content": (
            "员工年假规则：入职满一年享受5天年假，满三年享受7天年假，满五年享受10天年假。"
            "合同到期前60天由HR发起续签流程。员工可在自助系统查询剩余年假与合同到期日期。"
        ),
    },
    {
        "filename": "知识库接入规范.txt",
        "department": "IT",
        "content": (
            "知识库接入规范：上传文件支持PDF、DOCX、TXT。"
            "文档切分使用800字符和150字符重叠。"
            "向量模型使用text-embedding-3-small，索引采用HNSW。"
        ),
    },
    {
        "filename": "薪酬查询权限说明.txt",
        "department": "HR",
        "content": (
            "薪酬查询权限说明：员工仅可查看本人的薪酬总包。"
            "直属经理可查看本人和直属下属的薪酬概览。"
            "HR管理员可查看全公司的完整薪酬明细。"
        ),
    },
]
