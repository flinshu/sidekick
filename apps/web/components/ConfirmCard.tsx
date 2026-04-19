"use client";

export type ConfirmCardData = {
  tool_name: string;
  note?: string;
  preview?: Record<string, unknown> | null;
};

export function ConfirmCard({
  data,
  onConfirm,
  onCancel,
  loading,
}: {
  data: ConfirmCardData;
  onConfirm: () => void;
  onCancel: () => void;
  loading?: boolean;
}) {
  return (
    <div className="rounded-lg border-2 border-amber-400 bg-amber-50 p-4 text-sm shadow-sm dark:border-amber-700 dark:bg-amber-950/30">
      <div className="mb-2 flex items-center gap-2">
        <span className="rounded bg-amber-500 px-2 py-0.5 text-xs font-bold text-white">
          需要确认
        </span>
        <span className="font-mono text-zinc-700 dark:text-zinc-200">{data.tool_name}</span>
      </div>
      {data.note ? (
        <p className="mb-3 text-xs text-zinc-700 dark:text-zinc-300">{data.note}</p>
      ) : null}
      {data.preview ? (
        <pre className="mb-3 max-h-48 overflow-auto rounded bg-white p-2 text-[11px] dark:bg-zinc-900">
          {JSON.stringify(data.preview, null, 2)}
        </pre>
      ) : null}
      <div className="flex justify-end gap-2">
        <button
          type="button"
          disabled={loading}
          onClick={onCancel}
          className="rounded-md border border-zinc-300 bg-white px-3 py-1 text-xs hover:bg-zinc-50 disabled:opacity-50 dark:border-zinc-700 dark:bg-zinc-900 dark:hover:bg-zinc-800"
        >
          取消
        </button>
        <button
          type="button"
          disabled={loading}
          onClick={onConfirm}
          className="rounded-md bg-emerald-600 px-3 py-1 text-xs font-medium text-white hover:bg-emerald-700 disabled:opacity-50"
        >
          {loading ? "处理中..." : "确认"}
        </button>
      </div>
    </div>
  );
}
