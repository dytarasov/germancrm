"use client";

import { useEffect, useRef, useState } from "react";
import { cx } from "./ui";

/**
 * Инлайн-поле с автосохранением: сохраняет на blur/Enter, если значение изменилось.
 * Esc — отмена правки (blur без сохранения). Пустая строка = null (комиссия: null ≠ 0).
 */
export function InlineField({
  label,
  value,
  onSave,
  placeholder,
  hint,
  type = "text",
  mono,
  multiline,
}: {
  label: string;
  value: string | null;
  onSave: (v: string | null) => void;
  placeholder?: string;
  hint?: string;
  type?: "text" | "money" | "number" | "date";
  mono?: boolean;
  multiline?: boolean;
}) {
  const normalized = value ?? "";
  const [draft, setDraft] = useState(normalized);
  // Esc: setDraft не успевает примениться до blur — флагом пропускаем commit со стейл-значением.
  const skipCommit = useRef(false);

  useEffect(() => {
    setDraft(value ?? "");
  }, [value]);

  const commit = () => {
    if (skipCommit.current) {
      skipCommit.current = false;
      return;
    }
    const v = draft.trim();
    if (v === (value ?? "")) return;
    onSave(v === "" ? null : v);
  };

  const cancel = (el: HTMLElement) => {
    skipCommit.current = true;
    setDraft(normalized);
    el.blur();
  };

  const cls = cx(
    "w-full rounded-md border border-transparent bg-transparent px-2 py-2 text-[16px] transition-colors lg:py-1 lg:text-[13px]",
    "hover:border-line focus:border-line focus:bg-surface",
    (mono || type === "money" || type === "number") && "font-mono tnum",
  );

  return (
    <div>
      <div className="mb-0.5 px-2 text-[11.5px] font-medium text-muted">{label}</div>
      {multiline ? (
        <textarea
          className={cx(cls, "min-h-16 resize-y")}
          value={draft}
          placeholder={placeholder ?? "—"}
          onChange={(e) => setDraft(e.target.value)}
          onBlur={commit}
          onKeyDown={(e) => {
            if (e.key === "Escape") cancel(e.target as HTMLTextAreaElement);
          }}
        />
      ) : (
        <input
          className={cls}
          type={type === "date" ? "date" : "text"}
          inputMode={type === "money" || type === "number" ? "decimal" : undefined}
          value={draft}
          placeholder={placeholder ?? "—"}
          onChange={(e) => setDraft(e.target.value)}
          onBlur={commit}
          onKeyDown={(e) => {
            if (e.key === "Enter") (e.target as HTMLInputElement).blur();
            if (e.key === "Escape") cancel(e.target as HTMLInputElement);
          }}
        />
      )}
      {hint && <div className="mt-0.5 px-2 text-[11.5px] text-muted">{hint}</div>}
    </div>
  );
}
