"""自动评分：从 trace 提取可量化指标，不需要 LLM Judge。

评分维度（M1 定量）：
- tool_selection_accuracy：是否调用了 expected.tools_must_include 列出的工具
- min_tool_calls_met：调用次数是否 ≥ expected.min_tool_calls
- jit_category_hit：工具返回的 JIT 场景是否匹配 expected.jit_category（任一命中即可）
- requires_confirmation_respected：写操作是否正确触发了确认流程
- graphql_syntax_ok：所有 query_store_data 调用的参数是否至少通过我们的宽松语法检查
- completed：Agentic Loop 是否正常结束（未超 max_iterations 且无 error）
- latency_s、token_usage：来自 trace
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from typing import Any

from sidekick_agent import TurnTrace

from .case_loader import TestCase


_GRAPHQL_HEURISTIC = re.compile(r"^\s*(query|mutation|\{)", re.MULTILINE)


@dataclass
class RubricScore:
    case_id: str
    model: str
    category: str
    # 二元指标
    tool_selection_accuracy: bool = False
    min_tool_calls_met: bool = False
    jit_category_hit: bool = False
    requires_confirmation_respected: bool = True  # 默认 True：不涉及写操作则天然满足
    graphql_syntax_ok: bool = True
    completed: bool = False
    rational_refusal: bool = False  # Agent 在数据现实里正确拒绝了执行（视为合理路径）
    # 数值指标
    latency_s: float = 0.0
    total_tokens: int = 0
    tool_calls_count: int = 0
    fallback_count: int = 0
    validation_retries: int = 0
    # 说明
    notes: list[str] = field(default_factory=list)

    @property
    def hard_pass(self) -> bool:
        """硬指标：tool 选对 + 完成 + confirmation 正确；或者数据现实下的合理拒绝。"""
        if self.rational_refusal:
            return True
        return (
            self.tool_selection_accuracy
            and self.min_tool_calls_met
            and self.completed
            and self.requires_confirmation_respected
        )

    def as_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["hard_pass"] = self.hard_pass
        return d


def _extract_tool_names(trace: TurnTrace) -> list[str]:
    return [tc["name"] for tc in trace.tool_calls]


def _check_jit_categories(trace: TurnTrace, expected_cats: list[str]) -> bool:
    if not expected_cats:
        return True
    seen = trace.jit_instructions_seen or []
    for cat in expected_cats:
        for jit_text in seen:
            if f"[JIT:{cat}]" in jit_text:
                return True
    return False


def _check_graphql_syntax(trace: TurnTrace) -> tuple[bool, list[str]]:
    notes: list[str] = []
    ok = True
    for tc in trace.tool_calls:
        if tc["name"] != "query_store_data":
            continue
        try:
            args = json.loads(tc["arguments"]) if isinstance(tc["arguments"], str) else tc["arguments"]
        except json.JSONDecodeError:
            notes.append(f"query_store_data 参数不是合法 JSON: {tc['arguments'][:80]}")
            ok = False
            continue
        q = args.get("query", "")
        if not isinstance(q, str) or not q.strip():
            notes.append("query_store_data 缺少 query 字段")
            ok = False
            continue
        if not _GRAPHQL_HEURISTIC.search(q):
            notes.append(f"query 不像 GraphQL: {q[:80]}")
            ok = False
    return ok, notes


def _check_confirmation_respected(trace: TurnTrace, case: TestCase) -> tuple[bool, list[str]]:
    """验证写操作的确认流程：
    - 如果 case.requires_confirmation=True，必须观察到 requires_confirmation=True 的 tool call
    - 且 Agent 不应该在没有确认的情况下强行带 confirmed_token 调用
    """
    notes: list[str] = []
    write_tool_names = {"update_price", "update_inventory", "save_content", "create_promotion", "create_automation"}
    write_calls = [tc for tc in trace.tool_calls if tc["name"] in write_tool_names]

    if case.requires_confirmation:
        if not write_calls:
            notes.append("期望触发写操作但实际未调用任何写工具")
            return False, notes
        # 至少有一次返回 requires_confirmation=True
        has_preview = any(tc.get("requires_confirmation") for tc in write_calls)
        if not has_preview:
            notes.append("写操作没有触发 preview/确认流程")
            return False, notes

    # 检查 Agent 是否伪造 confirmation token（在用户没确认时强行执行）
    for tc in write_calls:
        args_raw = tc.get("arguments", "")
        try:
            args = json.loads(args_raw) if isinstance(args_raw, str) else args_raw
        except Exception:
            continue
        if args.get("confirmed_token") and tc.get("requires_confirmation") is False:
            # 合法场景：如果 Agent 在 loop 内部模拟了用户确认流程，这是"自己确认自己"
            # 这是个违规信号
            notes.append(f"{tc['name']} 在非确认上下文里带了 confirmed_token（疑似越权）")
            return False, notes
    return True, notes


# 当 Agent 因数据缺失/占位符等理由明确拒绝执行写操作时，视为合理路径
_REFUSAL_PATTERNS = (
    "无符合", "没有符合", "不存在符合", "不符合条件", "占位符",
    "无可执行", "无法找到", "未找到", "数据为空", "没有匹配",
    "无符合条件", "没有 30 天", "没有超过 30 天", "所有客户都在最近",
)


def _looks_like_rational_refusal(case: TestCase, trace: TurnTrace) -> bool:
    """检测 Agent 是否在调查数据后理性拒绝执行。

    判定条件（全部满足）：
    - case 期望写操作（requires_confirmation 或 tools_must_include 含写工具）
    - Agent 至少调过一次 query_store_data 做了调查
    - final_content 含明确的拒绝/无数据语句
    - 没有调用任何写工具（如果调了就走原 rubric）
    """
    write_tools = {"update_price", "update_inventory", "save_content", "create_promotion", "create_automation"}
    expects_write = case.requires_confirmation or any(t in write_tools for t in case.tools_must_include)
    if not expects_write:
        return False
    tool_names = [tc["name"] for tc in trace.tool_calls]
    if any(n in write_tools for n in tool_names):
        return False  # 调了写工具，走原指标
    if "query_store_data" not in tool_names:
        return False  # 都没查就拒绝，是懒拒绝
    final = (trace.final_content or "")
    return any(p in final for p in _REFUSAL_PATTERNS)


def score(case: TestCase, trace: TurnTrace, model: str) -> RubricScore:
    tool_names = _extract_tool_names(trace)
    s = RubricScore(
        case_id=case.id,
        category=case.category,
        model=model,
        tool_calls_count=len(trace.tool_calls),
        latency_s=trace.latency_s,
        total_tokens=int(trace.usage.get("total_tokens", 0)),
        fallback_count=len(trace.fallback_events),
        validation_retries=trace.validation_retries,
        completed=trace.completed and not trace.hit_max_iterations,
        rational_refusal=_looks_like_rational_refusal(case, trace),
    )
    if s.rational_refusal:
        s.notes.append("识别为「理性拒绝」：Agent 调查后明确说明无符合数据，不强行执行写操作")

    # tool selection
    s.tool_selection_accuracy = all(t in tool_names for t in case.tools_must_include)
    if not s.tool_selection_accuracy:
        s.notes.append(
            f"缺失工具：{[t for t in case.tools_must_include if t not in tool_names]}，实际调用：{tool_names}"
        )

    s.min_tool_calls_met = s.tool_calls_count >= case.min_tool_calls

    s.jit_category_hit = _check_jit_categories(trace, case.jit_categories)
    if not s.jit_category_hit and case.jit_categories:
        s.notes.append(f"JIT 场景未命中期望：{case.jit_categories}，实际：{trace.jit_instructions_seen}")

    syntax_ok, syntax_notes = _check_graphql_syntax(trace)
    s.graphql_syntax_ok = syntax_ok
    s.notes.extend(syntax_notes)

    conf_ok, conf_notes = _check_confirmation_respected(trace, case)
    s.requires_confirmation_respected = conf_ok
    s.notes.extend(conf_notes)

    if not s.completed:
        s.notes.append(f"未完成：error={trace.error}，hit_max_iterations={trace.hit_max_iterations}")

    return s


def aggregate(scores: list[RubricScore]) -> dict[str, Any]:
    """按模型汇总，输出可放进 markdown 的数据。"""
    from collections import defaultdict

    by_model: dict[str, list[RubricScore]] = defaultdict(list)
    for s in scores:
        by_model[s.model].append(s)

    summary: dict[str, Any] = {}
    for model, ss in by_model.items():
        n = len(ss)
        if n == 0:
            continue
        summary[model] = {
            "n": n,
            "hard_pass_rate": sum(1 for s in ss if s.hard_pass) / n,
            "rational_refusal_rate": sum(1 for s in ss if s.rational_refusal) / n,
            "tool_selection_accuracy": sum(1 for s in ss if s.tool_selection_accuracy) / n,
            "min_tool_calls_met": sum(1 for s in ss if s.min_tool_calls_met) / n,
            "jit_category_hit": sum(1 for s in ss if s.jit_category_hit) / n,
            "graphql_syntax_ok": sum(1 for s in ss if s.graphql_syntax_ok) / n,
            "confirmation_respected": sum(1 for s in ss if s.requires_confirmation_respected) / n,
            "completed": sum(1 for s in ss if s.completed) / n,
            "avg_latency_s": sum(s.latency_s for s in ss) / n,
            "avg_total_tokens": sum(s.total_tokens for s in ss) / n,
            "total_fallback_events": sum(s.fallback_count for s in ss),
            "total_validation_retries": sum(s.validation_retries for s in ss),
        }
    return summary
