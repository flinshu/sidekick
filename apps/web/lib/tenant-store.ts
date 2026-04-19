/**
 * 简易租户上下文：localStorage 持久化当前激活的 shop_domain。
 * 不引入 Zustand/Redux 等额外依赖。
 */
"use client";

import { useCallback, useEffect, useState } from "react";

const STORAGE_KEY = "sidekick.active_tenant";

export function useActiveTenant(defaultDomain: string | null) {
  const [active, setActive] = useState<string | null>(defaultDomain);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored) setActive(stored);
    else if (defaultDomain) setActive(defaultDomain);
  }, [defaultDomain]);

  const update = useCallback((domain: string) => {
    setActive(domain);
    if (typeof window !== "undefined") localStorage.setItem(STORAGE_KEY, domain);
  }, []);

  return [active, update] as const;
}
