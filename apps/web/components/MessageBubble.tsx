"use client";

import type { ToolCallEntry } from "./ToolCallCard";
import { ToolCallCard } from "./ToolCallCard";

export type ChatMessage = {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  toolCalls?: ToolCallEntry[];
  loading?: boolean;
};

export function MessageBubble({ msg }: { msg: ChatMessage }) {
  const isUser = msg.role === "user";
  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
      <div
        className={`max-w-[85%] rounded-lg px-3 py-2 text-sm ${
          isUser
            ? "bg-blue-600 text-white"
            : "bg-zinc-100 text-zinc-900 dark:bg-zinc-800 dark:text-zinc-100"
        }`}
      >
        {msg.toolCalls && msg.toolCalls.length > 0 ? (
          <div className="mb-2 space-y-1">
            {msg.toolCalls.map((tc, i) => (
              <ToolCallCard key={i} tc={tc} />
            ))}
          </div>
        ) : null}
        {msg.content ? (
          <div className="whitespace-pre-wrap break-words">{msg.content}</div>
        ) : msg.loading ? (
          <div className="flex items-center gap-1 text-zinc-500">
            <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-current [animation-delay:-0.3s]" />
            <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-current [animation-delay:-0.15s]" />
            <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-current" />
          </div>
        ) : null}
      </div>
    </div>
  );
}
