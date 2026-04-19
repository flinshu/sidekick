"use client";

import { useEffect, useState } from "react";
import type { ConversationSummary } from "@/lib/api";
import { fetchConversations } from "@/lib/api";

export function ConversationSidebar({
  shopDomain,
  activeId,
  onSelect,
  onNew,
  refreshKey,
}: {
  shopDomain: string | null;
  activeId: string | null;
  onSelect: (id: string) => void;
  onNew: () => void;
  refreshKey: number;
}) {
  const [list, setList] = useState<ConversationSummary[]>([]);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (!shopDomain) return;
    let cancelled = false;
    setLoading(true);
    fetchConversations(shopDomain)
      .then((rows) => {
        if (!cancelled) setList(rows);
        if (!cancelled) setErr(null);
      })
      .catch((e) => {
        if (!cancelled) setErr(String(e));
      })
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [shopDomain, refreshKey]);

  return (
    <aside className="flex w-64 flex-col border-r border-zinc-200 bg-zinc-50 dark:border-zinc-800 dark:bg-zinc-950">
      <div className="border-b border-zinc-200 p-3 dark:border-zinc-800">
        <button
          type="button"
          onClick={onNew}
          className="w-full rounded-md bg-blue-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-blue-700"
        >
          + 新建会话
        </button>
      </div>
      <div className="flex-1 overflow-y-auto p-2">
        {loading ? (
          <div className="px-2 text-xs text-zinc-500">加载中…</div>
        ) : err ? (
          <div className="px-2 text-xs text-rose-600">{err}</div>
        ) : list.length === 0 ? (
          <div className="px-2 text-xs text-zinc-500">暂无会话</div>
        ) : (
          list.map((c) => (
            <button
              type="button"
              key={c.id}
              onClick={() => onSelect(c.id)}
              className={`mb-1 w-full rounded-md px-2 py-1.5 text-left text-xs transition ${
                activeId === c.id
                  ? "bg-blue-100 text-blue-900 dark:bg-blue-950/50 dark:text-blue-200"
                  : "hover:bg-zinc-200 dark:hover:bg-zinc-900"
              }`}
              title={c.title ?? c.id}
            >
              <div className="truncate font-medium">{c.title ?? "(无标题)"}</div>
              <div className="text-[10px] text-zinc-500">{new Date(c.updated_at).toLocaleString()}</div>
            </button>
          ))
        )}
      </div>
    </aside>
  );
}
