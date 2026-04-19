"use client";

import { useState } from "react";

export type ToolCallEntry = {
  name: string;
  arguments: string;
  ok: boolean;
  requires_confirmation: boolean;
  error?: string | null;
};

const STATUS_DOT: Record<string, string> = {
  pending: "bg-amber-400 animate-pulse",
  ok: "bg-emerald-500",
  fail: "bg-rose-500",
};

export function ToolCallCard({ tc }: { tc: ToolCallEntry }) {
  const [open, setOpen] = useState(false);
  const status = tc.ok === false ? "fail" : "ok";
  let argsPreview = tc.arguments;
  try {
    const parsed = JSON.parse(tc.arguments);
    argsPreview = JSON.stringify(parsed, null, 2);
  } catch {
    /* keep raw */
  }
  return (
    <div className="rounded-md border border-zinc-200 bg-zinc-50 p-2 text-xs dark:border-zinc-800 dark:bg-zinc-900">
      <button
        type="button"
        className="flex w-full items-center gap-2 text-left"
        onClick={() => setOpen((s) => !s)}
      >
        <span className={`h-2 w-2 rounded-full ${STATUS_DOT[status]}`} />
        <span className="font-mono text-zinc-700 dark:text-zinc-300">{tc.name}</span>
        {tc.requires_confirmation ? (
          <span className="rounded bg-amber-100 px-1.5 text-[10px] text-amber-800 dark:bg-amber-950 dark:text-amber-200">
            需要确认
          </span>
        ) : null}
        {tc.error ? (
          <span className="truncate text-rose-600">{tc.error.slice(0, 40)}</span>
        ) : (
          <span className="text-zinc-500">{open ? "▼" : "▶"}</span>
        )}
      </button>
      {open ? (
        <pre className="mt-2 max-h-60 overflow-auto whitespace-pre-wrap break-all rounded bg-zinc-100 p-2 text-[11px] dark:bg-zinc-950">
          {argsPreview}
        </pre>
      ) : null}
    </div>
  );
}
