"use client";

import { useEffect, useState } from "react";

export interface ToastItem {
  id: number;
  title: string;
  kind: "ok" | "err";
  actionLabel?: string;
  onAction?: () => void;
  /** уже уходит — проигрывается анимация ухода, потом элемент удаляется */
  leaving?: boolean;
}

let seq = 0;
let items: ToastItem[] = [];
const subs = new Set<(t: ToastItem[]) => void>();

function emit() {
  for (const f of subs) f([...items]);
}

const EXIT_MS = 150;

export function dismissToast(id: number) {
  if (!items.some((t) => t.id === id && !t.leaving)) return;
  items = items.map((t) => (t.id === id ? { ...t, leaving: true } : t));
  emit();
  window.setTimeout(() => {
    items = items.filter((t) => t.id !== id);
    emit();
  }, EXIT_MS);
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
    // телефон: по центру снизу, над «полоской» iPhone; десктоп: правый нижний угол
    <div className="pointer-events-none fixed inset-x-4 bottom-[calc(env(safe-area-inset-bottom)+1rem)] z-50 flex flex-col items-center gap-2 sm:inset-x-auto sm:right-4 sm:bottom-4 sm:items-end">
      {list.map((t) => (
        <div
          key={t.id}
          role="status"
          data-leaving={t.leaving || undefined}
          // transition, а не keyframes: тосты сыплются подряд, переход не дёргается
          // при перебивании. Приходит снизу и уходит вниз же.
          className="pointer-events-auto flex max-w-full items-center gap-3 rounded-lg border border-line bg-surface px-3.5 py-2.5 shadow-lg shadow-black/5 transition duration-200 ease-out starting:translate-y-2 starting:opacity-0 data-leaving:translate-y-2 data-leaving:opacity-0 data-leaving:duration-150"
        >
          <span
            className={
              "inline-block size-1.5 shrink-0 rounded-full " +
              (t.kind === "ok" ? "bg-green-500" : "bg-red-500")
            }
          />
          <span className="max-w-80 min-w-0 text-[13px]">{t.title}</span>
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
