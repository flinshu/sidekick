"""把 LLM 发来的 tool call 分发给 sidekick_tools 的对应 async 函数。

此处统一处理：
- 参数校验（缺字段）
- 等待确认（二阶段写操作）
- 序列化返回值给 LLM
"""
from __future__ import annotations

import json
import logging
from typing import Any, Awaitable, Callable

from sidekick_tools import (
    ShopifyClient,
    ToolResult,
    create_automation,
    create_promotion,
    query_store_data,
    save_content,
    update_inventory,
    update_price,
)

logger = logging.getLogger(__name__)

ToolCallable = Callable[..., Awaitable[ToolResult]]


_DISPATCH: dict[str, ToolCallable] = {
    "query_store_data": query_store_data,  # type: ignore[dict-item]
    "update_price": update_price,  # type: ignore[dict-item]
    "update_inventory": update_inventory,  # type: ignore[dict-item]
    "save_content": save_content,  # type: ignore[dict-item]
    "create_promotion": create_promotion,  # type: ignore[dict-item]
    "create_automation": create_automation,  # type: ignore[dict-item]
}


class ToolDispatchError(ValueError):
    """参数格式错误等不抛 exception 到 LLM，而是序列化为失败 ToolResult。"""


def _parse_args(raw: str | dict[str, Any]) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as e:
        # 修复 Qwen 等模型 tool args 末尾被截断 1-2 个 } 的常见情况
        repaired = _try_repair_truncated_json(raw)
        if repaired is not None:
            logger.warning("工具参数 JSON 截断，已自动修复（补 }/]）")
            parsed = repaired
        else:
            raise ToolDispatchError(f"工具参数 JSON 解析失败：{e}") from e
    if not isinstance(parsed, dict):
        raise ToolDispatchError("工具参数必须是 JSON 对象")
    return parsed


def _try_repair_truncated_json(raw: str) -> dict[str, Any] | None:
    """尝试通过追加 }/] 修复末尾被截断的 JSON。最多补 5 个字符。"""
    text = raw.rstrip()
    # 计算所需的闭合
    depth_obj = text.count("{") - text.count("}")
    depth_arr = text.count("[") - text.count("]")
    if depth_obj < 0 or depth_arr < 0:
        return None
    if depth_obj == 0 and depth_arr == 0:
        return None  # 不是缺右括号问题
    if depth_obj + depth_arr > 5:
        return None  # 缺得太多，不像是单纯截断
    # 先补数组、再补对象（典型嵌套 ...]} 顺序）
    suffix = "]" * depth_arr + "}" * depth_obj
    candidate = text + suffix
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        return None


_WRITE_TOOLS: frozenset[str] = frozenset(
    {"update_price", "update_inventory", "save_content", "create_promotion", "create_automation"}
)


async def dispatch_tool_call(
    name: str,
    arguments: str | dict[str, Any],
    *,
    shopify_client: ShopifyClient | None = None,
    confirmed_tokens: set[str] | None = None,
) -> ToolResult:
    """把 LLM 返回的 tool_call（function name + JSON args）转换为真实工具调用。

    HIL 安全：写工具的 Phase 2（带 confirmed_token）只允许当 token 出现在
    `confirmed_tokens` 集合里——这个集合由 caller 从 DB 已确认的 checkpoint 派生。
    Agent 凭空伪造 confirmed_token 会被拒绝。
    """
    if name not in _DISPATCH:
        return ToolResult(
            ok=False,
            error=f"未知工具：{name}。可用工具见 system prompt 的 Tools 段落。",
        )
    try:
        args = _parse_args(arguments)
    except ToolDispatchError as e:
        return ToolResult(ok=False, error=str(e))

    # HIL 防伪：写工具带 confirmed_token 时必须出现在白名单
    if name in _WRITE_TOOLS:
        ct = args.get("confirmed_token")
        if ct:
            allowed = confirmed_tokens or set()
            if ct not in allowed:
                return ToolResult(
                    ok=False,
                    error=(
                        "未授权的 confirmed_token：用户尚未在 UI 上点击「确认」按钮。"
                        "请先以 preview 形式向商家展示操作，等待用户在确认卡片上点击确认。"
                    ),
                )

    # 注入共享 ShopifyClient 避免每次新建
    if shopify_client is not None:
        args.setdefault("client", shopify_client)

    func = _DISPATCH[name]
    try:
        result = await func(**args)
    except TypeError as e:
        return ToolResult(ok=False, error=f"工具参数不符：{e}")
    except Exception as e:  # noqa: BLE001
        logger.exception("工具 %s 执行异常", name)
        return ToolResult(ok=False, error=f"工具执行异常：{e}")

    if not isinstance(result, ToolResult):
        return ToolResult(ok=False, error="工具返回值类型错误")
    return result


def serialize_tool_result(result: ToolResult, *, max_chars: int = 8000) -> str:
    """把 ToolResult 序列化为发给 LLM 的字符串。

    保留 jit_instruction / requires_confirmation / confirmation_token / preview
    这些让 LLM 做决策的字段。data 过大时截断。
    """
    payload: dict[str, Any] = {
        "ok": result.ok,
        "jit_instruction": result.jit_instruction,
    }
    if result.error:
        payload["error"] = result.error
    if result.requires_confirmation:
        payload["requires_confirmation"] = True
        payload["confirmation_token"] = result.confirmation_token
        payload["preview"] = result.preview
    if result.data:
        encoded = json.dumps(result.data, ensure_ascii=False, default=str)
        if len(encoded) > max_chars:
            encoded = encoded[:max_chars] + "...[truncated]"
        try:
            payload["data"] = json.loads(encoded) if "truncated" not in encoded else encoded
        except json.JSONDecodeError:
            payload["data"] = encoded
    return json.dumps(payload, ensure_ascii=False)
