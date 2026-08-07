"use client";

import { ReactNode, ButtonHTMLAttributes, InputHTMLAttributes, SelectHTMLAttributes, TextareaHTMLAttributes, useEffect } from "react";

export function cx(...parts: Array<string | false | null | undefined>): string {
  return parts.filter(Boolean).join(" ");
}

/** Базовый вид контрола-триггера (как Input) — для кастомных пикеров/селектов. */
export const controlCls =
  "flex h-10 items-center rounded-md border border-line bg-surface px-2.5 text-left text-[16px] transition-colors hover:bg-surface2/50 lg:h-8 lg:text-[13px]";

type BtnVariant = "primary" | "outline" | "ghost" | "danger";

export function Button({
  variant = "outline",
  className,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: BtnVariant }) {
  const styles: Record<BtnVariant, string> = {
    primary: "bg-accent text-white hover:opacity-90 border border-transparent",
    outline: "border border-line bg-surface hover:bg-surface2",
    ghost: "hover:bg-surface2 border border-transparent",
    danger: "border border-transparent text-red-600 dark:text-red-400 hover:bg-red-500/10",
  };
  return (
    <button
      className={cx(
        "inline-flex h-8 items-center gap-1.5 rounded-md px-3 text-[13px] font-medium transition-colors disabled:pointer-events-none disabled:opacity-50",
        styles[variant],
        className,
      )}
      {...props}
    />
  );
}

export function Input({ className, ...props }: InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      className={cx(
        "h-10 w-full rounded-md border border-line bg-surface px-2.5 text-[16px] placeholder:text-muted/70 lg:h-8 lg:text-[13px]",
        className,
      )}
      {...props}
    />
  );
}

export function Select({ className, ...props }: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select
      className={cx(
        "h-10 rounded-md border border-line bg-surface px-2 text-[16px] lg:h-8 lg:text-[13px]",
        className,
      )}
      {...props}
    />
  );
}

export function Textarea({ className, ...props }: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <textarea
      className={cx(
        "w-full rounded-md border border-line bg-surface px-2.5 py-1.5 text-[16px] placeholder:text-muted/70 lg:text-[13px]",
        className,
      )}
      {...props}
    />
  );
}

export function Card({ className, children }: { className?: string; children: ReactNode }) {
  return (
    <div className={cx("rounded-lg border border-line bg-surface", className)}>{children}</div>
  );
}

export function Section({
  title,
  actions,
  children,
  className,
}: {
  title: string;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <Card className={className}>
      <div className="flex min-h-10 flex-wrap items-center justify-between gap-x-3 gap-y-1.5 border-b border-line px-4 py-1.5">
        <h2 className="text-[13px] font-semibold">{title}</h2>
        {actions}
      </div>
      <div className="p-3 sm:p-4">{children}</div>
    </Card>
  );
}

export function Badge({
  className,
  children,
}: {
  className?: string;
  children: ReactNode;
}) {
  return (
    <span
      className={cx(
        "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11.5px] font-medium whitespace-nowrap",
        className,
      )}
    >
      {children}
    </span>
  );
}

export function EmptyState({ title, hint }: { title: string; hint?: string }) {
  return (
    <div className="flex flex-col items-center gap-2 py-10 text-center">
      <div className="airmail w-24" />
      <p className="mt-2 text-[13px] font-medium">{title}</p>
      {hint && <p className="max-w-sm text-[12.5px] text-muted">{hint}</p>}
    </div>
  );
}

export function Seg<T extends string>({
  value,
  onChange,
  options,
}: {
  value: T;
  onChange: (v: T) => void;
  options: { value: T; label: string }[];
}) {
  return (
    <div className="inline-flex h-8 items-center gap-0.5 rounded-md border border-line bg-surface p-0.5">
      {options.map((o) => (
        <button
          key={o.value}
          onClick={() => onChange(o.value)}
          className={cx(
            "h-6.5 rounded px-2.5 text-[12.5px] font-medium transition-colors",
            value === o.value ? "bg-surface2 text-ink" : "text-muted hover:text-ink",
          )}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

export function Modal({
  open,
  onClose,
  title,
  children,
  wide,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  children: ReactNode;
  wide?: boolean;
}) {
  useEffect(() => {
    if (!open) return;
    const h = (e: KeyboardEvent) => {
      // Radix Popover/Select при закрытии по Esc делает preventDefault —
      // не закрываем модалку тем же нажатием.
      if (e.key === "Escape" && !e.defaultPrevented) onClose();
    };
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [open, onClose]);

  if (!open) return null;
  return (
    <div
      className="fixed inset-0 z-40 flex items-stretch justify-center bg-black/30 sm:items-start sm:p-4 sm:pt-[12vh]"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        role="dialog"
        aria-modal
        className={cx(
          "flex h-full w-full flex-col border-line bg-surface shadow-xl",
          "sm:h-auto sm:max-h-[80vh] sm:rounded-xl sm:border",
          wide ? "sm:max-w-2xl" : "sm:max-w-md",
        )}
      >
        <div className="flex h-12 shrink-0 items-center justify-between border-b border-line pr-1.5 pl-4 pt-[env(safe-area-inset-top)] sm:h-11 sm:pt-0">
          <h2 className="text-[13.5px] font-semibold">{title}</h2>
          <button
            aria-label="Закрыть"
            className="flex size-10 items-center justify-center rounded-md text-[17px] text-muted hover:bg-surface2 hover:text-ink sm:size-8"
            onClick={onClose}
          >
            ×
          </button>
        </div>
        <div className="flex-1 overflow-y-auto p-4 pb-[calc(env(safe-area-inset-bottom)+1rem)] sm:flex-none sm:pb-4">
          {children}
        </div>
      </div>
    </div>
  );
}

export function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1 block text-[12px] font-medium text-muted">{label}</span>
      {children}
    </label>
  );
}

export function Spinner() {
  return (
    <span className="inline-block size-3.5 animate-spin rounded-full border-2 border-line border-t-accent align-middle" />
  );
}
