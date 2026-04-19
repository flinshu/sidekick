"use client";

import type { Tenant } from "@/lib/api";

export function TenantSwitcher({
  tenants,
  active,
  onChange,
}: {
  tenants: Tenant[];
  active: string | null;
  onChange: (shopDomain: string) => void;
}) {
  return (
    <div className="flex items-center gap-2">
      <span className="text-xs text-zinc-500">店铺：</span>
      <select
        className="rounded-md border border-zinc-300 bg-white px-2 py-1 text-sm dark:border-zinc-700 dark:bg-zinc-900"
        value={active ?? ""}
        onChange={(e) => onChange(e.target.value)}
      >
        {tenants.length === 0 ? (
          <option value="">无可用租户</option>
        ) : (
          tenants.map((t) => (
            <option key={t.shop_domain} value={t.shop_domain}>
              {t.display_name}
            </option>
          ))
        )}
      </select>
      {active ? (
        <span className="rounded-full bg-emerald-100 px-2 py-0.5 text-[10px] font-medium text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300">
          {active.split(".")[0]}
        </span>
      ) : null}
    </div>
  );
}
