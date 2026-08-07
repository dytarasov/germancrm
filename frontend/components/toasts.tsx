"use client";

import { useEffect, useState } from "react";

export interface ToastItem {
  id: number;
  title: string;
  kind: "ok" | "err";
  actionLabel?: string;
  onAction?: () => void;
}

let seq = 0;
let items: ToastItem[] = [];
const subs = new Set<(t: ToastItem[]) => void>();

function emit() {
  for (const f of subs) f([...items]);
}

export function dismissToast(id: number) {
  items = items.filter((t) => t.id !== id);
  emit();
}

export function pushToast(t: Omit<ToastItem, "id">, ttlMs = 5000) {
  const item: ToastItem = { ...t, id: ++seq };
  items = [...items.slice(-3), item];
  emit();
  window.setTimeout(() => dismissToast(item.id), ttlMs);
}

/** Тост «Сохранено · Отменить» — единая точка undo. */
export function toastSaved(undo?: () => void, title = "Сохранено") {
  pushToast(
    { title, kind: "ok", actionLabel: undo ? "Отменить" : undefined, onAction: undo },
    undo ? 7000 : 3500,
  );
}

export function toastError(message: string) {
  pushToast({ title: message, kind: "err" }, 8000);
}

export function Toaster() {
  const [list, setList] = useState<ToastItem[]>([]);

  useEffect(() => {
    subs.add(setList);
    return () => {
      subs.delete(setList);
    };
  }, []);

  return (
    <div className="pointer-events-none fixed right-4 bottom-4 z-50 flex flex-col gap-2">
      {list.map((t) => (
        <div
          key={t.id}
          role="status"
          className="pointer-events-auto flex items-center gap-3 rounded-lg border border-line bg-surface px-3.5 py-2.5 shadow-lg shadow-black/5"
          style={{ animation: "toast-in 150ms ease-out" }}
        >
          <span
            className={
              "inline-block size-1.5 shrink-0 rounded-full " +
              (t.kind === "ok" ? "bg-green-500" : "bg-red-500")
            }
          />
          <span className="max-w-80 text-[13px]">{t.title}</span>
          {t.actionLabel && (
            <button
              className="text-[13px] font-medium text-accent hover:underline"
              onClick={() => {
                t.onAction?.();
                dismissToast(t.id);
              }}
            >
              {t.actionLabel}
            </button>
          )}
          <button
            aria-label="Закрыть"
            className="ml-1 text-muted hover:text-ink"
            onClick={() => dismissToast(t.id)}
          >
            ×
          </button>
        </div>
      ))}
    </div>
  );
}
