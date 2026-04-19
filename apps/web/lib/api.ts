/**
 * 后端 API 客户端 + SSE 流式 chat 抽象。
 * - API base 默认指向 localhost:8001（M2 PoC）
 * - 所有租户范围接口必须带 X-Shop-Domain 头
 */

export const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8001";

export type Tenant = {
  shop_domain: string;
  display_name: string;
  locale: string;
};

export type ConversationSummary = {
  id: string;
  title: string | null;
  updated_at: string;
  message_count: number;
};

export type MessageDto = {
  role: "user" | "assistant" | "tool" | "system";
  content: string | null;
  tool_calls?: Array<{
    id?: string;
    type?: string;
    function: { name: string; arguments: string };
  }> | null;
  tool_call_id?: string | null;
  name?: string | null;
  created_at?: string;
};

export type PendingConfirmationDto = {
  tool_name: string;
  confirmation_token: string;
  preview?: Record<string, unknown> | null;
  note?: string | null;
};

export type ConversationDetail = {
  id: string;
  title: string | null;
  messages: MessageDto[];
  pending_confirmations?: PendingConfirmationDto[];
};

export type SseEvent =
  | { event: "conversation_id"; data: { conversation_id: string } }
  | { event: "tool_call"; data: { name: string; arguments: string; ok: boolean; requires_confirmation: boolean; error?: string | null } }
  | { event: "confirmation_required"; data: { tool_name: string; note: string } }
  | { event: "token"; data: { content: string } }
  | { event: "done"; data: Record<string, unknown> }
  | { event: "error"; data: { error: string } };

function tenantHeaders(shopDomain: string): HeadersInit {
  return { "X-Shop-Domain": shopDomain, "Content-Type": "application/json" };
}

export async function fetchTenants(): Promise<Tenant[]> {
  const r = await fetch(`${API_BASE}/api/tenants`);
  if (!r.ok) throw new Error(`tenants ${r.status}`);
  return r.json();
}

export async function fetchConversations(shopDomain: string): Promise<ConversationSummary[]> {
  const r = await fetch(`${API_BASE}/api/conversations`, { headers: tenantHeaders(shopDomain) });
  if (!r.ok) throw new Error(`conversations ${r.status}`);
  return r.json();
}

export async function fetchConversation(shopDomain: string, id: string): Promise<ConversationDetail> {
  const r = await fetch(`${API_BASE}/api/conversations/${id}`, { headers: tenantHeaders(shopDomain) });
  if (!r.ok) throw new Error(`conversation ${id}: ${r.status}`);
  return r.json();
}

export async function postConfirm(
  shopDomain: string,
  payload: { conversation_id: string; confirmation_token: string; decision: "confirm" | "cancel"; note?: string }
): Promise<{ ok: boolean; decision: string }> {
  const r = await fetch(`${API_BASE}/api/confirm`, {
    method: "POST",
    headers: tenantHeaders(shopDomain),
    body: JSON.stringify(payload),
  });
  if (!r.ok) throw new Error(`confirm ${r.status}`);
  return r.json();
}

export type AsyncJob = {
  task_id: string;
  status: "pending" | "running" | "succeeded" | "failed";
  result?: unknown;
  error?: string;
};

/** M2.5 占位：前端可以在 ChatPanel 旁边显示异步任务进度。
 * 后端 /api/jobs/<task_id> 等真接 Celery 时启用。 */
export async function fetchJobStatus(shopDomain: string, taskId: string): Promise<AsyncJob> {
  const r = await fetch(`${API_BASE}/api/jobs/${taskId}`, { headers: tenantHeaders(shopDomain) });
  if (!r.ok) throw new Error(`job ${taskId}: ${r.status}`);
  return r.json();
}

/** 流式 chat：fetch + ReadableStream 解析 SSE，调 onEvent 回调。 */
export async function streamChat(
  shopDomain: string,
  payload: { conversation_id?: string; message: string; task_type?: string; model_override?: string },
  onEvent: (e: SseEvent) => void,
  signal?: AbortSignal
): Promise<void> {
  const r = await fetch(`${API_BASE}/api/chat`, {
    method: "POST",
    headers: tenantHeaders(shopDomain),
    body: JSON.stringify(payload),
    signal,
  });
  if (!r.ok || !r.body) {
    const text = await r.text().catch(() => "");
    throw new Error(`chat ${r.status}: ${text.slice(0, 200)}`);
  }
  const reader = r.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    // SSE 块分隔 \n\n
    let idx;
    while ((idx = buffer.indexOf("\n\n")) >= 0) {
      const chunk = buffer.slice(0, idx);
      buffer = buffer.slice(idx + 2);
      const event = parseSseChunk(chunk);
      if (event) onEvent(event);
    }
  }
}

function parseSseChunk(chunk: string): SseEvent | null {
  let event = "";
  let dataStr = "";
  for (const line of chunk.split("\n")) {
    if (line.startsWith("event:")) event = line.slice(6).trim();
    else if (line.startsWith("data:")) dataStr += line.slice(5).trim();
  }
  if (!event) return null;
  try {
    const data = dataStr ? JSON.parse(dataStr) : {};
    return { event, data } as SseEvent;
  } catch {
    return { event: "error", data: { error: `bad SSE data: ${dataStr.slice(0, 100)}` } };
  }
}
