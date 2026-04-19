"""工具调用与确认的 Pydantic 模型。"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ToolResult(BaseModel):
    """所有工具的统一返回包装：data + jit_instruction。"""

    ok: bool = True
    data: dict[str, Any] = Field(default_factory=dict)
    jit_instruction: str = ""
    error: str | None = None
    requires_confirmation: bool = False
    """对写操作：True 时 Agent 必须先把 preview 给商家确认。"""

    confirmation_token: str | None = None
    """与 preview 一起返回，确认后回传同一个 token。"""

    preview: dict[str, Any] | None = None
    """写操作的 preview 内容（before/after、影响范围）。"""


class WritePreview(BaseModel):
    """写操作 preview 通用结构。"""

    operation: str
    summary: str
    before: dict[str, Any] | None = None
    after: dict[str, Any] | None = None
    impact: str | None = None


class ConfirmDecision(BaseModel):
    decision: Literal["confirm", "cancel"]
    confirmation_token: str
    note: str | None = None
