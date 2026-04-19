"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { fetchConversation, postConfirm, streamChat } from "@/lib/api";
import type { ToolCallEntry } from "./ToolCallCard";
import type { ChatMessage } from "./MessageBubble";
import { MessageBubble } from "./MessageBubble";
import { ConfirmCard } from "./ConfirmCard";

type ConfirmPending = {
  conversationId: string;
  toolName: string;
  note?: string;
  preview?: Record<string, unknown> | null;
  confirmationToken: string;
};

type Props = {
  shopDomain: string | null;
  conversationId: string | null;
  /** 单调递增 key：sidebar 点击会 bump，触发从 DB 拉历史；SSE 中获得的新 id 不 bump（避免吞掉乐观渲染） */
  loadKey: number;
  onConversationChange: (id: string) => void;
  onAfterTurn: () => void;
};

export function ChatPanel({ shopDomain, conversationId, loadKey, onConversationChange, onAfterTurn }: Props) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [confirmPending, setConfirmPending] = useState<ConfirmPending | null>(null);
  const [confirmLoading, setConfirmLoading] = useState(false);
  const scrollerRef = useRef<HTMLDivElement>(null);

  // 显式加载已有会话（仅 sidebar 点击会触发：loadKey 变了）
  useEffect(() => {
    if (!shopDomain) return;
    // 切会话必须清掉上一会话残留的 HIL 卡片，否则会串显示
    setConfirmPending(null);
    setError(null);
    if (!conversationId) {
      setMessages([]);
      return;
    }
    let cancelled = false;
    fetchConversation(shopDomain, conversationId)
      .then((d) => {
        if (cancelled) return;
        // 把连续多条 assistant 合并显示——assistant 中"只有 tool_calls 没 content"的就跳过
        const display: ChatMessage[] = d.messages
          .filter((m) => (m.role === "user" || m.role === "assistant") && (m.content ?? "").trim() !== "")
          .map((m, i) => ({
            id: `${conversationId}-${i}`,
            role: m.role as "user" | "assistant",
            content: m.content ?? "",
          }));
        setMessages(display);
        // 刷新/HMR 后从后端恢复未决的 HIL 卡片（取最新一条即可）
        const pc = d.pending_confirmations?.[d.pending_confirmations.length - 1];
        if (pc) {
          setConfirmPending({
            conversationId,
            toolName: pc.tool_name,
            note: pc.note ?? undefined,
            preview: pc.preview ?? null,
            confirmationToken: pc.confirmation_token,
          });
        }
      })
      .catch((e) => !cancelled && setError(String(e)));
    return () => {
      cancelled = true;
    };
  }, [shopDomain, loadKey]); // 注意：依赖 loadKey 而不是 conversationId

  useEffect(() => {
    scrollerRef.current?.scrollTo({ top: scrollerRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, busy]);

  const send = useCallback(async () => {
    if (!shopDomain || !input.trim() || busy) return;
    const userText = input.trim();
    setInput("");
    setError(null);
    setBusy(true);
    setConfirmPending(null);

    const userMsg: ChatMessage = { id: `local-u-${Date.now()}`, role: "user", content: userText };
    const assistantMsg: ChatMessage = {
      id: `local-a-${Date.now()}`,
      role: "assistant",
      content: "",
      toolCalls: [],
      loading: true,
    };
    setMessages((prev) => [...prev, userMsg, assistantMsg]);

    const localToolCalls: ToolCallEntry[] = [];
    let assistantText = "";
    let convId = conversationId;

    try {
      await streamChat(
        shopDomain,
        { conversation_id: conversationId ?? undefined, message: userText },
        (e) => {
          if (e.event === "conversation_id") {
            convId = e.data.conversation_id;
            if (!conversationId && convId) onConversationChange(convId);
          } else if (e.event === "tool_call") {
            const tc: ToolCallEntry = {
              name: e.data.name,
              arguments: e.data.arguments,
              ok: e.data.ok,
              requires_confirmation: e.data.requires_confirmation,
              error: e.data.error ?? null,
            };
            localToolCalls.push(tc);
            setMessages((prev) =>
              prev.map((m) =>
                m.id === assistantMsg.id ? { ...m, toolCalls: [...localToolCalls] } : m
              )
            );
          } else if (e.event === "confirmation_required") {
            const d = e.data as {
              tool_name: string;
              confirmation_token: string;
              preview?: Record<string, unknown> | null;
              note?: string;
            };
            setConfirmPending({
              conversationId: convId ?? "",
              toolName: d.tool_name,
              note: d.note,
              preview: d.preview,
              confirmationToken: d.confirmation_token,
            });
          } else if (e.event === "token") {
            assistantText += e.data.content;
            setMessages((prev) =>
              prev.map((m) =>
                m.id === assistantMsg.id
                  ? { ...m, content: assistantText, loading: false }
                  : m
              )
            );
          } else if (e.event === "error") {
            setError(String(e.data.error ?? "未知错误"));
          }
        }
      );
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
      setMessages((prev) =>
        prev.map((m) => (m.id === assistantMsg.id ? { ...m, loading: false } : m))
      );
      onAfterTurn();
    }
  }, [shopDomain, input, busy, conversationId, onConversationChange, onAfterTurn]);

  const handleConfirm = useCallback(
    async (decision: "confirm" | "cancel") => {
      if (!shopDomain || !confirmPending) return;
      setConfirmLoading(true);
      try {
        await postConfirm(shopDomain, {
          conversation_id: confirmPending.conversationId,
          confirmation_token: confirmPending.confirmationToken,
          decision,
        });
        // 自动追发 follow-up 消息触发 Agent 继续（白名单已含此 token）
        // Agent 应从对话历史里读到上一条 tool 返回的 confirmation_token，并在新的 tool call 里复用
        const followup =
          decision === "confirm"
            ? `已确认。请用上一条工具返回的 confirmation_token 继续执行。`
            : `已取消。请告知操作未执行，并询问其他需求。`;
        setConfirmPending(null);
        setInput(followup);
        // 触发自动发送
        setTimeout(() => {
          (document.querySelector("form") as HTMLFormElement | null)?.requestSubmit();
        }, 50);
      } catch (e) {
        setError(String(e));
      } finally {
        setConfirmLoading(false);
      }
    },
    [shopDomain, confirmPending]
  );

  return (
    <section className="flex h-full flex-1 flex-col">
      <div ref={scrollerRef} className="flex-1 overflow-y-auto p-4 space-y-3">
        {messages.length === 0 ? (
          <div className="mx-auto max-w-md text-center text-sm text-zinc-500">
            <div className="mb-2 text-3xl">👋</div>
            <p className="mb-1">向 Sidekick 提问，例如：</p>
            <ul className="mt-2 space-y-1 text-left text-xs">
              <li>· 列出店里前 5 个商品的 title 和价格</li>
              <li>· 上周订单数和总销售额</li>
              <li>· 哪些客户消费最多？Top 3</li>
            </ul>
          </div>
        ) : (
          messages.map((m) => <MessageBubble key={m.id} msg={m} />)
        )}
        {confirmPending && confirmPending.conversationId === conversationId ? (
          <ConfirmCard
            data={{
              tool_name: confirmPending.toolName,
              note: confirmPending.note,
              preview: confirmPending.preview,
            }}
            onConfirm={() => handleConfirm("confirm")}
            onCancel={() => handleConfirm("cancel")}
            loading={confirmLoading}
          />
        ) : null}
        {error ? (
          <div className="rounded-md border border-rose-300 bg-rose-50 p-2 text-xs text-rose-800 dark:border-rose-800 dark:bg-rose-950/40 dark:text-rose-200">
            ⚠️ {error}
            <button
              type="button"
              className="ml-2 underline"
              onClick={() => setError(null)}
            >
              关闭
            </button>
          </div>
        ) : null}
      </div>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          send();
        }}
        className="border-t border-zinc-200 bg-white p-3 dark:border-zinc-800 dark:bg-zinc-900"
      >
        <div className="flex gap-2">
          <input
            type="text"
            value={input}
            disabled={busy || !shopDomain}
            onChange={(e) => setInput(e.target.value)}
            placeholder={shopDomain ? "输入消息，回车发送…" : "请先在右上角选择店铺"}
            className="flex-1 rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm focus:border-blue-500 focus:outline-none disabled:opacity-50 dark:border-zinc-700 dark:bg-zinc-950"
          />
          <button
            type="submit"
            disabled={busy || !shopDomain || !input.trim()}
            className="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
          >
            {busy ? "..." : "发送"}
          </button>
        </div>
      </form>
    </section>
  );
}
