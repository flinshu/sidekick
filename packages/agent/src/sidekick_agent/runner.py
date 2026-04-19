"""Agentic Loop 运行时：LLM ↔ 工具循环 + JIT 指令注入 + 模型 fallback + 重试。

设计选择：
- **不用 PydanticAI.Agent 自带的 run loop**。原因：PydanticAI 的 model adapter 目前对
  DashScope / LiteLLM 兼容不佳，且 M1 要精确控制 JIT 注入、二阶段确认、fallback 事件记录，
  自己写一个 80 行的循环更透明。Pydantic 本身依然用于 schema 验证。
- **LiteLLM 作为统一 LLM 调用层**：一个 acompletion 搞定 OpenAI / Anthropic / DashScope。
- **工具调用**：OpenAI-style tools schema，LiteLLM 会翻译到各 provider。

每次 run_turn() 对应一次商家的输入消息。函数内部跑 Agentic Loop 直到：
- 模型产生无 tool_call 的 assistant 消息（完成）；或
- 达到 max_iterations 上限（强制终止，返回 partial）。
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any

import litellm
from pydantic import BaseModel, ValidationError

from sidekick_tools import ShopifyClient

from .prompts import build_system_prompt
from .routing import RouterConfig, load_router_config
from .tool_dispatcher import dispatch_tool_call, serialize_tool_result
from .tool_schemas import TOOL_SCHEMAS

logger = logging.getLogger(__name__)

# LiteLLM 默认会跑 telemetry / 回调，关掉让 M1 输出干净
litellm.telemetry = False
litellm.drop_params = True  # 某些 provider 不支持的参数自动忽略


@dataclass
class ConversationMessage:
    role: str  # "system" / "user" / "assistant" / "tool"
    content: str | None = None
    tool_calls: list[dict[str, Any]] | None = None
    tool_call_id: str | None = None
    name: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"role": self.role}
        if self.content is not None:
            d["content"] = self.content
        if self.tool_calls:
            d["tool_calls"] = self.tool_calls
        if self.tool_call_id:
            d["tool_call_id"] = self.tool_call_id
        if self.name:
            d["name"] = self.name
        return d


@dataclass
class TurnTrace:
    """单轮对话的追踪记录——M1 评估就看这些字段。"""

    task_type: str
    attempted_models: list[str] = field(default_factory=list)
    successful_model: str | None = None
    iterations: int = 0
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    jit_instructions_seen: list[str] = field(default_factory=list)
    final_content: str | None = None
    fallback_events: list[dict[str, Any]] = field(default_factory=list)
    validation_retries: int = 0
    error: str | None = None
    latency_s: float = 0.0
    usage: dict[str, Any] = field(default_factory=dict)
    completed: bool = False
    hit_max_iterations: bool = False
    pending_confirmations: list[dict[str, Any]] = field(default_factory=list)
    """HIL：本轮中工具返回 requires_confirmation=True 的 (token, tool_name, args, preview) 列表"""


@dataclass
class TurnResult:
    messages: list[ConversationMessage]
    trace: TurnTrace
    structured_output: BaseModel | None = None


class AgentRunner:
    """单 Agent + JIT + 多模型路由的执行器。"""

    def __init__(
        self,
        *,
        config: RouterConfig | None = None,
        shopify_client: ShopifyClient | None = None,
        system_prompt: str | None = None,
    ) -> None:
        self.config = config or load_router_config()
        self.system_prompt = system_prompt or build_system_prompt()
        self._shopify = shopify_client  # 若 None，每次调用时懒加载

    async def _ensure_shopify(self) -> ShopifyClient:
        if self._shopify is None:
            self._shopify = ShopifyClient()
        return self._shopify

    async def aclose(self) -> None:
        if self._shopify is not None:
            await self._shopify.aclose()
            self._shopify = None

    async def run_turn(
        self,
        user_message: str,
        *,
        history: list[ConversationMessage] | None = None,
        task_type: str | None = None,
        model_override: str | None = None,
        structured_output: type[BaseModel] | None = None,
        confirmed_tokens: set[str] | None = None,
    ) -> TurnResult:
        """跑一次完整的 Agentic Loop。

        Args:
            user_message: 商家这一轮输入。
            history: 之前轮次的消息（可选）。
            task_type: 对应 llm_router.yaml 的 route key。
            model_override: 临时指定模型，覆盖 routing。
            structured_output: 可选的 Pydantic 模型，强制最终输出匹配此 schema。

        Returns:
            TurnResult：含所有消息、trace、最终结构化结果（如指定）。
        """
        route = self.config.resolve(task_type)
        trace = TurnTrace(task_type=route.task_type)

        # 模型选择列表：override 优先
        models_to_try: list[str] = (
            [model_override] if model_override else list(route.all_models())
        )

        # 初始化 message 列表
        messages: list[ConversationMessage] = [
            ConversationMessage(role="system", content=self.system_prompt)
        ]
        if history:
            messages.extend(history)
        messages.append(ConversationMessage(role="user", content=user_message))

        start = time.time()
        try:
            await self._agentic_loop(messages, models_to_try, trace, confirmed_tokens=confirmed_tokens or set())
        except Exception as e:  # noqa: BLE001
            logger.exception("Agentic Loop 失败")
            trace.error = str(e)
        trace.latency_s = time.time() - start

        # 结构化输出验证
        structured: BaseModel | None = None
        if structured_output is not None and trace.final_content:
            structured = await self._validate_structured(
                trace.final_content, structured_output, messages, models_to_try, trace
            )

        return TurnResult(messages=messages, trace=trace, structured_output=structured)

    # ---------- 内部实现 ----------

    async def _agentic_loop(
        self,
        messages: list[ConversationMessage],
        models_to_try: list[str],
        trace: TurnTrace,
        *,
        confirmed_tokens: set[str] | None = None,
    ) -> None:
        for iteration in range(self.config.agent_max_iterations):
            trace.iterations = iteration + 1
            response = await self._call_llm_with_fallback(messages, models_to_try, trace)
            if response is None:
                trace.error = trace.error or "所有模型都失败"
                return

            choice = response["choices"][0]
            msg = choice["message"]
            tool_calls = msg.get("tool_calls") or []
            assistant_msg = ConversationMessage(
                role="assistant",
                content=msg.get("content"),
                tool_calls=tool_calls if tool_calls else None,
            )
            messages.append(assistant_msg)

            # 累计 token 用量
            usage = response.get("usage") or {}
            if usage:
                for k in ("prompt_tokens", "completion_tokens", "total_tokens"):
                    trace.usage[k] = trace.usage.get(k, 0) + usage.get(k, 0)

            if not tool_calls:
                trace.final_content = msg.get("content") or ""
                trace.completed = True
                return

            # 执行每个 tool call
            shopify = await self._ensure_shopify()
            for call in tool_calls:
                fn = (call.get("function") or {})
                name = fn.get("name", "")
                arguments = fn.get("arguments", "")
                result = await dispatch_tool_call(
                    name,
                    arguments,
                    shopify_client=shopify,
                    confirmed_tokens=confirmed_tokens,
                )
                trace.tool_calls.append(
                    {
                        "name": name,
                        "arguments": arguments,
                        "ok": result.ok,
                        "requires_confirmation": result.requires_confirmation,
                        "error": result.error,
                    }
                )
                if result.jit_instruction:
                    trace.jit_instructions_seen.append(result.jit_instruction[:60])
                # HIL：写工具 Phase 1 → 记录 pending confirmation 供 caller 持久化
                if result.requires_confirmation and result.confirmation_token:
                    import json as _json

                    try:
                        parsed_args = _json.loads(arguments) if isinstance(arguments, str) else arguments
                    except _json.JSONDecodeError:
                        parsed_args = {"raw": arguments}
                    trace.pending_confirmations.append(
                        {
                            "tool_name": name,
                            "tool_args": parsed_args,
                            "confirmation_token": result.confirmation_token,
                            "preview": result.preview,
                        }
                    )
                tool_content = serialize_tool_result(result)
                messages.append(
                    ConversationMessage(
                        role="tool",
                        content=tool_content,
                        tool_call_id=call.get("id"),
                        name=name,
                    )
                )
        # 超过上限
        trace.hit_max_iterations = True
        trace.error = f"max_iterations ({self.config.agent_max_iterations}) 超出"

    async def _call_llm_with_fallback(
        self,
        messages: list[ConversationMessage],
        models_to_try: list[str],
        trace: TurnTrace,
    ) -> dict[str, Any] | None:
        openai_messages = [m.to_dict() for m in messages]
        last_error: Exception | None = None
        for model in models_to_try:
            trace.attempted_models.append(model)
            litellm_model = _to_litellm_model(model)
            extra = _extra_kwargs_for(model)
            for attempt in range(self.config.agent_max_retries_per_call):
                try:
                    response = await litellm.acompletion(
                        model=litellm_model,
                        messages=openai_messages,
                        tools=TOOL_SCHEMAS,
                        max_tokens=self.config.max_tokens,
                        temperature=self.config.temperature,
                        **extra,
                    )
                    trace.successful_model = model
                    return response.model_dump() if hasattr(response, "model_dump") else dict(response)
                except Exception as e:  # noqa: BLE001
                    last_error = e
                    logger.warning(
                        "LLM 调用失败 model=%s attempt=%d/%d: %s",
                        model,
                        attempt + 1,
                        self.config.agent_max_retries_per_call,
                        e,
                    )
                    await asyncio.sleep(0.5 * (attempt + 1))
            trace.fallback_events.append({"model_failed": model, "error": str(last_error)})
        return None

    async def _validate_structured(
        self,
        text: str,
        schema: type[BaseModel],
        messages: list[ConversationMessage],
        models_to_try: list[str],
        trace: TurnTrace,
    ) -> BaseModel | None:
        """尝试把 final_content 解析为指定 schema，失败则反馈错误让 LLM 重试。

        尝试次数上限 = 初次 + agent_max_retries_per_call 次重试。
        """
        import json
        import re

        max_attempts = self.config.agent_max_retries_per_call + 1
        for attempt in range(max_attempts):
            try:
                t = text.strip()
                candidate: Any
                if t.startswith("{"):
                    candidate = json.loads(t)
                else:
                    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", t, re.DOTALL)
                    candidate = json.loads(m.group(1)) if m else None
                if candidate is None:
                    raise ValueError("无法从回复中提取 JSON")
                return schema.model_validate(candidate)
            except (json.JSONDecodeError, ValueError, ValidationError) as e:
                if attempt == max_attempts - 1:
                    trace.error = trace.error or f"结构化输出验证失败：{e}"
                    return None
                trace.validation_retries += 1
                feedback = (
                    f"你上一条回复无法解析为目标 schema `{schema.__name__}`：{e}\n"
                    f"请以合法 JSON 格式重新输出，且字段严格满足 schema。"
                )
                messages.append(ConversationMessage(role="user", content=feedback))
                response = await self._call_llm_with_fallback(messages, models_to_try, trace)
                if response is None:
                    return None
                msg = response["choices"][0]["message"]
                messages.append(
                    ConversationMessage(role="assistant", content=msg.get("content"))
                )
                text = msg.get("content") or ""
        return None


# ---------- helpers ----------


def _extra_kwargs_for(model: str) -> dict[str, Any]:
    """非默认 provider 需要的额外参数（api_base / api_key）。"""
    provider, _, _name = model.partition(":")
    if provider == "zhipu":
        api_key = os.environ.get("ZHIPU_API_KEY", "")
        return {
            "api_base": "https://open.bigmodel.cn/api/paas/v4/",
            "api_key": api_key,
        }
    return {}


def _to_litellm_model(model: str) -> str:
    """把我们的 provider:name 格式翻译到 LiteLLM 可识别的字符串。

    LiteLLM 的规则：
    - anthropic/claude-sonnet-4-5  对应 Anthropic 直连
    - openai/gpt-4o                对应 OpenAI
    - dashscope/qwen-max           需要走 openai 兼容 endpoint
    - zhipu/glm-4-plus             智谱 GLM，走 OpenAI 兼容 endpoint
    """
    provider, _, name = model.partition(":")
    if provider == "anthropic":
        return f"anthropic/{name}"
    if provider == "openai":
        return f"openai/{name}"
    if provider == "dashscope":
        # LiteLLM 支持 dashscope 原生：设置 DASHSCOPE_API_KEY
        os.environ.setdefault(
            "DASHSCOPE_API_BASE", "https://dashscope.aliyuncs.com/compatible-mode/v1"
        )
        api_key = os.environ.get("DASHSCOPE_API_KEY", "")
        if api_key:
            os.environ["OPENAI_API_KEY_DASHSCOPE"] = api_key
        return f"dashscope/{name}"
    if provider == "zhipu":
        # 智谱 GLM 系列：用 OpenAI 兼容 endpoint 访问
        # （LiteLLM 较新版有 zhipu 原生 provider，但 OpenAI compat 更稳）
        return f"openai/{name}"
    return model  # 已是 LiteLLM 格式
