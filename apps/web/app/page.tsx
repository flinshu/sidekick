"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import type { Tenant } from "@/lib/api";
import { fetchTenants } from "@/lib/api";
import { useActiveTenant } from "@/lib/tenant-store";
import { TenantSwitcher } from "@/components/TenantSwitcher";
import { ConversationSidebar } from "@/components/ConversationSidebar";
import { ChatPanel } from "@/components/ChatPanel";

export default function Home() {
  const [tenants, setTenants] = useState<Tenant[]>([]);
  const [loading, setLoading] = useState(true);
  const [bootError, setBootError] = useState<string | null>(null);

  useEffect(() => {
    fetchTenants()
      .then((rows) => {
        setTenants(rows);
        setBootError(null);
      })
      .catch((e) => setBootError(`无法连接后端 API：${e}`))
      .finally(() => setLoading(false));
  }, []);

  const defaultTenant = useMemo(() => tenants[0]?.shop_domain ?? null, [tenants]);
  const [active, setActive] = useActiveTenant(defaultTenant);

  const [activeConvId, setActiveConvId] = useState<string | null>(null);
  const [sidebarRefresh, setSidebarRefresh] = useState(0);
  const [loadKey, setLoadKey] = useState(0); // 仅 sidebar 选择会 bump，触发 ChatPanel 重新拉 DB

  const handleNew = useCallback(() => {
    setActiveConvId(null);
    setLoadKey((n) => n + 1); // 切到空白
  }, []);
  const handleSidebarSelect = useCallback((id: string) => {
    setActiveConvId(id);
    setLoadKey((n) => n + 1); // 显式触发 fetch
  }, []);
  const handleConversationChange = useCallback((id: string) => {
    // SSE 流中获得新 id：只更新 id，不触发 fetch（保留乐观状态）
    setActiveConvId(id);
  }, []);
  const handleAfterTurn = useCallback(() => setSidebarRefresh((n) => n + 1), []);

  return (
    <div className="flex h-screen flex-col bg-white dark:bg-zinc-950">
      <header className="flex items-center justify-between border-b border-zinc-200 bg-white px-4 py-2 dark:border-zinc-800 dark:bg-zinc-950">
        <div className="flex items-center gap-2">
          <span className="text-base font-semibold">Sidekick</span>
          <span className="rounded bg-zinc-100 px-1.5 py-0.5 text-[10px] text-zinc-600 dark:bg-zinc-800 dark:text-zinc-400">
            POC v0.2
          </span>
        </div>
        {!loading ? (
          <TenantSwitcher tenants={tenants} active={active} onChange={setActive} />
        ) : (
          <span className="text-xs text-zinc-500">加载租户…</span>
        )}
      </header>

      {bootError ? (
        <div className="border-b border-rose-300 bg-rose-50 p-2 text-xs text-rose-800 dark:border-rose-800 dark:bg-rose-950/40 dark:text-rose-200">
          ⚠️ {bootError}（确认 FastAPI 已启动：`uvicorn app.main:app --app-dir apps/api --port 8001`）
        </div>
      ) : null}

      <div className="flex flex-1 overflow-hidden">
        <ConversationSidebar
          shopDomain={active}
          activeId={activeConvId}
          onSelect={handleSidebarSelect}
          onNew={handleNew}
          refreshKey={sidebarRefresh}
        />
        <ChatPanel
          shopDomain={active}
          conversationId={activeConvId}
          loadKey={loadKey}
          onConversationChange={handleConversationChange}
          onAfterTurn={handleAfterTurn}
        />
      </div>
    </div>
  );
}
