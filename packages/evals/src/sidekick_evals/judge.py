"""LLM-as-Judge：用一个 LLM 对 Agent 的响应打 1-5 分。

设计：
- 默认 judge 模型 = qwen-max（等后面有其他 provider 时换成不同家）
- 一次请求评一条，不做并行，避免限流
- 返回 JudgeScore 结构化输出
"""
from __future__ import annotations

import json
import logging
from typing import Any

import litellm

from sidekick_agent import JudgeScore

from .case_loader import TestCase

logger = logging.getLogger(__name__)

litellm.telemetry = False
litellm.drop_params = True


JUDGE_SYSTEM_PROMPT = """你是一个严格的 LLM 评审员，正在评估一个电商智能助手的响应质量。

你会收到：
1. 用户原始问题
2. 期望的评分 rubric（由测试用例作者给定）
3. 智能助手的最终回复
4. 智能助手调用工具的简要记录

你的任务：根据 rubric 打分。

严格遵守以下规则：
- **overall**: 1-5 分综合质量
  - 5: 完美满足 rubric 所有维度
  - 4: 主要维度都满足，但有小瑕疵
  - 3: 基本满足但明显缺陷
  - 2: 有部分满足但多个关键维度失败
  - 1: 基本失败
- **tool_selection_correct**: 是否选对了工具（依据 rubric）
- **jit_instruction_followed**: 工具返回的 JIT 指令是否被遵循（比如"分析师模式"对应是否做了环比、"SEO ≤ 160 字符"是否遵守）
- **graphql_syntax_valid**: 如果生成了 GraphQL 查询，语法是否合法（字段存在、结构正确）。无 GraphQL 时填 null。
- **graphql_fields_reasonable**: 字段选择是否合理（不过度取字段、没漏关键字段）。无 GraphQL 时填 null。
- **reasoning**: 2-4 句话说明打分理由，具体到哪个 rubric 条目满足/不满足。

**必须**只返回合法 JSON，不要带 markdown 代码块包装。只输出一个 JSON 对象，符合 JudgeScore schema。"""


def _build_user_prompt(case: TestCase, final_content: str, tool_calls_summary: list[dict]) -> str:
    rubric_txt = "\n".join(f"- {item}" for item in case.rubric)
    tools_txt = (
        json.dumps(tool_calls_summary, ensure_ascii=False, indent=2)
        if tool_calls_summary
        else "（无工具调用）"
    )
    return f"""# 测试用例 {case.id} ({case.category})

## 用户问题
{case.question}

## Rubric（评分维度）
{rubric_txt}

## 助手工具调用记录
```json
{tools_txt}
```

## 助手最终回复
{final_content}

请严格按 rubric 评分，只返回 JSON。"""


async def judge_one(
    case: TestCase,
    final_content: str,
    tool_calls_summary: list[dict],
    *,
    judge_model: str = "dashscope/qwen-max",
) -> JudgeScore | None:
    """对单条响应打分。失败时返回 None。"""
    messages = [
        {"role": "system", "content": JUDGE_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": _build_user_prompt(case, final_content, tool_calls_summary),
        },
    ]
    try:
        resp = await litellm.acompletion(
            model=judge_model,
            messages=messages,
            max_tokens=500,
            temperature=0,
            response_format={"type": "json_object"},
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("Judge 调用失败：%s", e)
        return None
    try:
        content = resp["choices"][0]["message"]["content"]
        data = _extract_json(content)
        if data is None:
            return None
        return JudgeScore.model_validate(data)
    except Exception as e:  # noqa: BLE001
        logger.warning("Judge 结果解析失败：%s，content=%r", e, content[:200] if isinstance(content, str) else "")
        return None


def _extract_json(text: str) -> dict[str, Any] | None:
    t = text.strip()
    if t.startswith("{"):
        try:
            return json.loads(t)
        except json.JSONDecodeError:
            pass
    # try code block
    import re

    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", t, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    # 尝试第一个 { 到最后一个 }
    start = t.find("{")
    end = t.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(t[start : end + 1])
        except json.JSONDecodeError:
            pass
    return None
