"use client";

import type { OrderStatus } from "@/lib/api-types";
import { FLOW, STATUS_BAR, STATUS_LABEL, flowIndex } from "@/lib/status";
import { cx } from "./ui";

/** Мини-полоска маршрута для строк таблиц. */
export function RouteStepperMini({ status }: { status: OrderStatus }) {
  const idx = flowIndex(status);
  const terminal = idx === -1; // cancelled / refunded
  return (
    <div
      className={cx("flex w-24 gap-0.5", terminal && "opacity-35")}
      title={STATUS_LABEL[status]}
      aria-label={STATUS_LABEL[status]}
    >
      {FLOW.map((s, i) => (
        <span
          key={s}
          className={cx(
            "h-1 flex-1 rounded-full",
            !terminal && i <= idx ? STATUS_BAR[status] : "bg-line",
          )}
        />
      ))}
    </div>
  );
}

/**
 * Крупный кликабельный маршрут в карточке заказа.
 * Клик по сегменту двигает статус вперёд или назад — самое частое действие дня.
 */
export function RouteStepper({
  status,
  onSelect,
  busy,
}: {
  status: OrderStatus;
  onSelect: (s: OrderStatus) => void;
  busy?: boolean;
}) {
  const idx = flowIndex(status);
  const terminal = idx === -1;

  return (
    <div className={cx("grid grid-cols-6 gap-1.5", terminal && "pointer-events-none opacity-40")}>
      {FLOW.map((s, i) => {
        const reached = !terminal && i <= idx;
        const current = !terminal && i === idx;
        return (
          <button
            key={s}
            disabled={busy || current}
            onClick={() => onSelect(s)}
            title={i < idx ? `Откатить до «${STATUS_LABEL[s]}»` : `Перевести в «${STATUS_LABEL[s]}»`}
            className={cx(
              "group flex flex-col gap-1.5 rounded-md p-1.5 text-left transition-colors",
              !current && "hover:bg-surface2",
            )}
          >
            <span
              className={cx(
                "h-1.5 w-full rounded-full transition-colors",
                reached ? STATUS_BAR[status] : "bg-line group-hover:bg-muted/40",
                current && "ring-2 ring-accent/30",
              )}
            />
            <span
              className={cx(
                "text-[10px] leading-tight break-words sm:text-[11.5px]",
                current ? "font-semibold text-ink" : reached ? "text-ink/80" : "text-muted",
              )}
            >
              {STATUS_LABEL[s]}
            </span>
          </button>
        );
      })}
    </div>
  );
}
