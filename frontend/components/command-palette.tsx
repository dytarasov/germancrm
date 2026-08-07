"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { SearchResult } from "@/lib/api-types";
import { STATUS_LABEL } from "@/lib/status";
import { fmtMoney } from "@/lib/format";
import { cx } from "./ui";

interface Item {
  key: string;
  group: string;
  label: string;
  sub: string;
  href: string;
}

export function CommandPalette() {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const [debounced, setDebounced] = useState("");
  const [active, setActive] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen((v) => !v);
      }
      if (e.key === "Escape") setOpen(false);
    };
    const onOpen = () => setOpen(true);
    window.addEventListener("keydown", onKey);
    window.addEventListener("open-cmdk", onOpen);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("open-cmdk", onOpen);
    };
  }, []);

  useEffect(() => {
    if (open) {
      setQ("");
      setDebounced("");
      setActive(0);
      setTimeout(() => inputRef.current?.focus(), 30);
    }
  }, [open]);

  useEffect(() => {
    const t = setTimeout(() => setDebounced(q.trim()), 200);
    return () => clearTimeout(t);
  }, [q]);

  const { data } = useQuery({
    queryKey: ["search", debounced],
    queryFn: () => api.get<SearchResult>("/api/search", { q: debounced }),
    enabled: open && debounced.length >= 2,
    staleTime: 10_000,
  });

  const items: Item[] = useMemo(() => {
    if (!data) return [];
    const out: Item[] = [];
    for (const c of data.clients.slice(0, 5)) {
      out.push({
        key: `c${c.id}`,
        group: "Клиенты",
        label: c.name,
        sub: `${c.active_orders} акт. · долг ${fmtMoney(c.debt_usd)}`,
        href: `/clients/${c.id}`,
      });
    }
    for (const o of data.orders.slice(0, 7)) {
      out.push({
        key: `o${o.id}`,
        group: "Заказы",
        label: `#${o.id} · ${o.items}`,
        sub: `${o.client_name} · ${o.store} · ${STATUS_LABEL[o.status]}`,
        href: `/orders/${o.id}`,
      });
    }
    for (const t of data.tracks.slice(0, 5)) {
      out.push({
        key: `t${t.id}`,
        group: "Треки",
        label: t.tracking_number,
        sub: t.order_id ? `заказ #${t.order_id}` : "непривязан",
        href: t.order_id ? `/orders/${t.order_id}` : "/tracks",
      });
    }
    return out;
  }, [data]);

  useEffect(() => setActive(0), [items.length]);

  const go = (item: Item) => {
    setOpen(false);
    router.push(item.href);
  };

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center bg-black/30 sm:p-4 sm:pt-[14vh]"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) setOpen(false);
      }}
    >
      <div className="flex h-[100dvh] w-full flex-col overflow-hidden border-line bg-surface pt-[env(safe-area-inset-top)] shadow-xl sm:h-auto sm:max-w-lg sm:rounded-xl sm:border sm:pt-0">
        <div className="flex shrink-0 items-center border-b border-line">
          <input
            ref={inputRef}
            value={q}
            onChange={(e) => setQ(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "ArrowDown") {
                e.preventDefault();
                setActive((a) => Math.min(a + 1, items.length - 1));
              }
              if (e.key === "ArrowUp") {
                e.preventDefault();
                setActive((a) => Math.max(a - 1, 0));
              }
              if (e.key === "Enter" && items[active]) go(items[active]);
            }}
            placeholder="Имя клиента, номер заказа, трек…"
            className="h-12 w-full bg-transparent px-4 text-[16px] outline-none placeholder:text-muted/70 sm:text-[14px]"
          />
          <button
            className="mr-2 shrink-0 rounded-md px-2.5 py-2 text-[14px] font-medium text-accent sm:hidden"
            onClick={() => setOpen(false)}
          >
            Отмена
          </button>
        </div>
        <div className="flex-1 overflow-y-auto p-1.5 pb-[calc(env(safe-area-inset-bottom)+0.375rem)] sm:max-h-80 sm:flex-none sm:pb-1.5">
          {debounced.length < 2 ? (
            <p className="px-3 py-6 text-center text-[12.5px] text-muted">
              Минимум два символа
            </p>
          ) : items.length === 0 ? (
            <p className="px-3 py-6 text-center text-[12.5px] text-muted">Ничего не найдено</p>
          ) : (
            items.map((item, i) => (
              <button
                key={item.key}
                onClick={() => go(item)}
                onMouseEnter={() => setActive(i)}
                className={cx(
                  "flex w-full items-baseline justify-between gap-3 rounded-md px-3 py-2 text-left",
                  i === active && "bg-surface2",
                )}
              >
                <span className="min-w-0">
                  <span className="mr-2 text-[10.5px] tracking-wide text-muted uppercase">
                    {item.group}
                  </span>
                  <span className="text-[13px] font-medium">{item.label}</span>
                </span>
                <span className="shrink-0 text-[12px] text-muted">{item.sub}</span>
              </button>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
