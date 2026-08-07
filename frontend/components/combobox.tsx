"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import * as Popover from "@radix-ui/react-popover";
import { controlCls, cx } from "./ui";
import { Chevron } from "./select-box";

export interface ComboOption {
  value: string;
  label: string;
  sublabel?: string;
}

/**
 * Селект с текстовым поиском для длинных списков (клиенты, заказы, рейсы).
 * Клавиатура: ↑/↓ — по списку, Enter — выбрать, Esc — закрыть.
 */
export function Combobox({
  value,
  onChange,
  options,
  placeholder = "Выберите…",
  searchPlaceholder = "Поиск…",
  emptyText = "Ничего не найдено",
  className,
}: {
  value: string;
  onChange: (v: string) => void;
  options: ComboOption[];
  placeholder?: string;
  searchPlaceholder?: string;
  emptyText?: string;
  className?: string;
}) {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const [active, setActive] = useState(0);
  const listRef = useRef<HTMLDivElement>(null);

  const selected = options.find((o) => o.value === value);

  const filtered = useMemo(() => {
    const s = q.trim().toLowerCase();
    if (!s) return options;
    return options.filter((o) =>
      `${o.label} ${o.sublabel ?? ""}`.toLowerCase().includes(s),
    );
  }, [options, q]);

  useEffect(() => {
    if (open) {
      setQ("");
      setActive(0);
    }
  }, [open]);

  useEffect(() => setActive(0), [q]);

  useEffect(() => {
    listRef.current
      ?.querySelector('[data-active="true"]')
      ?.scrollIntoView({ block: "nearest" });
  }, [active]);

  const pick = (v: string) => {
    onChange(v);
    setOpen(false);
  };

  return (
    <Popover.Root open={open} onOpenChange={setOpen}>
      <Popover.Trigger asChild>
        <button
          type="button"
          className={cx(controlCls, "justify-between gap-2", !selected && "text-muted", className)}
        >
          <span className="truncate">{selected ? selected.label : placeholder}</span>
          <Chevron />
        </button>
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Content
          align="start"
          sideOffset={6}
          collisionPadding={8}
          className="z-50 w-[min(94vw,max(var(--radix-popover-trigger-width),18rem))] overflow-hidden rounded-lg border border-line bg-surface shadow-xl shadow-black/10"
        >
          <input
            autoFocus
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder={searchPlaceholder}
            className="h-11 w-full border-b border-line bg-transparent px-3 text-[16px] outline-none placeholder:text-muted/70 sm:h-9 sm:text-[13px]"
            onKeyDown={(e) => {
              if (e.key === "ArrowDown") {
                e.preventDefault();
                setActive((a) => Math.min(a + 1, filtered.length - 1));
              }
              if (e.key === "ArrowUp") {
                e.preventDefault();
                setActive((a) => Math.max(a - 1, 0));
              }
              if (e.key === "Enter") {
                e.preventDefault();
                if (filtered[active]) pick(filtered[active].value);
              }
              if (e.key === "Escape") setOpen(false);
            }}
          />
          <div ref={listRef} className="max-h-64 overflow-y-auto p-1">
            {filtered.length === 0 ? (
              <p className="px-3 py-4 text-center text-[12.5px] text-muted">{emptyText}</p>
            ) : (
              filtered.map((o, i) => (
                <button
                  key={o.value || "__empty__"}
                  type="button"
                  data-active={i === active ? "true" : undefined}
                  onMouseEnter={() => setActive(i)}
                  onClick={() => pick(o.value)}
                  className={cx(
                    "flex w-full flex-col items-start rounded-md px-2.5 py-2.5 text-left sm:py-1.5",
                    i === active && "bg-surface2",
                  )}
                >
                  <span
                    className={cx(
                      "w-full truncate text-[14px] sm:text-[13px]",
                      o.value === value && value !== "" && "font-medium text-accent",
                    )}
                  >
                    {o.label}
                  </span>
                  {o.sublabel && (
                    <span className="w-full truncate text-[11.5px] text-muted">{o.sublabel}</span>
                  )}
                </button>
              ))
            )}
          </div>
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  );
}
