"""把 .env 里的 MiniMax sk-cp- key 从 OPENAI_* 字段迁移到 ANTHROPIC_* 字段。

只动相关 7 行，其他内容原封不动。可重复执行。
"""
from pathlib import Path

ENV_PATH = Path(__file__).resolve().parents[1] / ".env"
text = ENV_PATH.read_text(encoding="utf-8")
lines = text.splitlines()

# 1. 提取已有值
def grab(prefix: str) -> str | None:
    for ln in lines:
        if ln.startswith(prefix + "="):
            return ln.split("=", 1)[1]
    return None

old_key = grab("OPENAI_API_KEY") or ""
old_model = grab("OPENAI_MODEL") or ""

# 2. 把 OPENAI_API_KEY 清空（避免 openai 协议被误启用）
new_lines = []
seen = set()
for ln in lines:
    if ln.startswith("OPENAI_API_KEY="):
        new_lines.append("OPENAI_API_KEY=")
        seen.add("OPENAI_API_KEY")
    elif ln.startswith("OPENAI_BASE_URL="):
        # 保留注释式占位，方便以后切回
        new_lines.append("OPENAI_BASE_URL=")
    elif ln.startswith("OPENAI_MODEL="):
        new_lines.append("OPENAI_MODEL=")
    elif ln.startswith("ANTHROPIC_API_KEY=") or ln.startswith("ANTHROPIC_BASE_URL=") or ln.startswith("ANTHROPIC_MODEL=") or ln.startswith("LLM_PROVIDER="):
        # 跳过旧的，待会儿统一追加
        continue
    else:
        new_lines.append(ln)

# 3. 在文件末尾追加 Anthropic 段
new_lines.append("")
new_lines.append("# ===== MiniMax Token Plan / Coding Plan（Anthropic 协议）=====")
new_lines.append("LLM_PROVIDER=anthropic")
new_lines.append(f"ANTHROPIC_API_KEY={old_key}")
new_lines.append("ANTHROPIC_BASE_URL=https://api.minimaxi.com/anthropic")
new_lines.append(f"ANTHROPIC_MODEL={old_model or 'MiniMax-M2.7'}")

ENV_PATH.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
print("✓ migrated")
print(f"  old OPENAI_API_KEY -> ANTHROPIC_API_KEY (length={len(old_key)})")
print(f"  ANTHROPIC_BASE_URL = https://api.minimaxi.com/anthropic")
print(f"  ANTHROPIC_MODEL    = {old_model or 'MiniMax-M2.7'}")
print(f"  LLM_PROVIDER       = anthropic")
