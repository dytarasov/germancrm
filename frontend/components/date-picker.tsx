"use client";

import { useState } from "react";
import * as Popover from "@radix-ui/react-popover";
import { DayPicker, type DateRange } from "react-day-picker";
import { format } from "date-fns";
import { ru } from "date-fns/locale";
import "react-day-picker/style.css";
import { Button, controlCls, cx } from "./ui";

function parseISO(s: string | null): Date | undefined {
  if (!s) return undefined;
  const d = new Date(s + "T00:00:00");
  return Number.isNaN(d.getTime()) ? undefined : d;
}

function toISO(d: Date): string {
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

/** «6 авг 2026» — короткий русский формат для триггеров и подписей. */
export function formatDateRu(iso: string | null | undefined): string {
  const d = parseISO(iso ?? null);
  return d ? format(d, "d MMM yyyy", { locale: ru }) : "—";
}

function CalendarIcon() {
  return (
    <svg
      className="size-3.5 shrink-0 text-muted"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      aria-hidden
    >
      <rect x="3" y="4" width="18" height="18" rx="2" />
      <path d="M16 2v4M8 2v4M3 10h18" />
    </svg>
  );
}

const popCls =
  "z-50 rounded-lg border border-line bg-surface p-2 shadow-xl shadow-black/10 outline-none";

/**
 * Пикер даты: кнопка в стиле Input + календарь (react-day-picker, локаль ru).
 * value/onChange — строки YYYY-MM-DD (как ходит в API), null = пусто.
 */
export function DatePicker({
  value,
  onChange,
  placeholder = "Выберите дату",
  clearable,
  className,
}: {
  value: string | null;
  onChange: (v: string | null) => void;
  placeholder?: string;
  clearable?: boolean;
  className?: string;
}) {
  const [open, setOpen] = useState(false);
  const selected = parseISO(value);

  return (
    <Popover.Root open={open} onOpenChange={setOpen}>
      <Popover.Trigger asChild>
        <button
          type="button"
          className={cx(controlCls, "gap-2", !selected && "text-muted", className)}
        >
          <CalendarIcon />
          {selected ? formatDateRu(value) : placeholder}
        </button>
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Content align="start" sideOffset={6} collisionPadding={8} className={popCls}>
          <DayPicker
            mode="single"
            locale={ru}
            weekStartsOn={1}
            showOutsideDays
            selected={selected}
            defaultMonth={selected}
            onSelect={(d) => {
              onChange(d ? toISO(d) : null);
              setOpen(false);
            }}
          />
          <div className="flex justify-between gap-2 border-t border-line px-1 pt-1.5">
            <Button
              variant="ghost"
              onClick={() => {
                onChange(toISO(new Date()));
                setOpen(false);
              }}
            >
              Сегодня
            </Button>
            {clearable && (
              <Button
                variant="ghost"
                onClick={() => {
                  onChange(null);
                  setOpen(false);
                }}
              >
                Очистить
              </Button>
            )}
          </div>
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  );
}

/** Пикер произвольного периода (range) — для /money. */
export function DateRangePicker({
  from,
  to,
  onChange,
  className,
}: {
  from: string | null;
  to: string | null;
  onChange: (from: string | null, to: string | null) => void;
  className?: string;
}) {
  const [open, setOpen] = useState(false);
  const range: DateRange | undefined = parseISO(from)
    ? { from: parseISO(from), to: parseISO(to) }
    : undefined;

  const label =
    from && to
      ? `${formatDateRu(from)} — ${formatDateRu(to)}`
      : from
        ? `${formatDateRu(from)} — …`
        : "Выберите период";

  return (
    <Popover.Root open={open} onOpenChange={setOpen}>
      <Popover.Trigger asChild>
        <button
          type="button"
          className={cx(controlCls, "gap-2", !from && "text-muted", className)}
        >
          <CalendarIcon />
          {label}
        </button>
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Content align="start" sideOffset={6} collisionPadding={8} className={popCls}>
          <DayPicker
            mode="range"
            locale={ru}
            weekStartsOn={1}
            showOutsideDays
            selected={range}
            defaultMonth={range?.from}
            onSelect={(r) => {
              onChange(r?.from ? toISO(r.from) : null, r?.to ? toISO(r.to) : null);
            }}
          />
          <div className="flex justify-between gap-2 border-t border-line px-1 pt-1.5">
            <Button
              variant="ghost"
              onClick={() => {
                onChange(null, null);
              }}
            >
              Очистить
            </Button>
            <Button variant="ghost" onClick={() => setOpen(false)}>
              Готово
            </Button>
          </div>
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  );
}
