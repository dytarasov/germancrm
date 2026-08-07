"use client";

import { ReactNode } from "react";
import * as RSelect from "@radix-ui/react-select";
import { controlCls, cx } from "./ui";

// Radix Select не допускает value="", а у нас "" = «все/не выбрано».
const EMPTY = "__empty__";

export function Chevron() {
  return (
    <svg
      className="size-3.5 shrink-0 text-muted"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      <path d="M6 9l6 6 6-6" />
    </svg>
  );
}

/** Стилизованный селект (Radix) с прежним API: value/onChange строками, "" допустимо. */
export function SelectBox({
  value,
  onChange,
  options,
  placeholder,
  className,
}: {
  value: string;
  onChange: (v: string) => void;
  options: { value: string; label: ReactNode }[];
  placeholder?: string;
  className?: string;
}) {
  return (
    <RSelect.Root
      value={value === "" ? EMPTY : value}
      onValueChange={(v) => onChange(v === EMPTY ? "" : v)}
    >
      <RSelect.Trigger
        aria-label={placeholder}
        className={cx(controlCls, "justify-between gap-2", className)}
      >
        <span className="truncate">
          <RSelect.Value placeholder={placeholder} />
        </span>
        <RSelect.Icon>
          <Chevron />
        </RSelect.Icon>
      </RSelect.Trigger>
      <RSelect.Portal>
        <RSelect.Content
          position="popper"
          sideOffset={6}
          collisionPadding={8}
          className="z-50 min-w-[var(--radix-select-trigger-width)] overflow-hidden rounded-lg border border-line bg-surface shadow-xl shadow-black/10"
        >
          <RSelect.Viewport className="max-h-72 p-1">
            {options.map((o) => (
              <RSelect.Item
                key={o.value || EMPTY}
                value={o.value === "" ? EMPTY : o.value}
                className="relative flex cursor-pointer items-center rounded-md py-2.5 pr-2.5 pl-7 text-[14px] outline-none select-none data-[highlighted]:bg-surface2 sm:py-1.5 sm:text-[13px]"
              >
                <RSelect.ItemIndicator className="absolute left-2 font-semibold text-accent">
                  ✓
                </RSelect.ItemIndicator>
                <RSelect.ItemText>{o.label}</RSelect.ItemText>
              </RSelect.Item>
            ))}
          </RSelect.Viewport>
        </RSelect.Content>
      </RSelect.Portal>
    </RSelect.Root>
  );
}
