"use client";

import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "@/lib/api";
import type { OrderDetail, OrderListItem, OrderStatus } from "@/lib/api-types";
import { FLOW, STATUS_BAR, STATUS_LABEL, flowIndex } from "@/lib/status";
import { toastError, toastSaved } from "./toasts";
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

/** Смена статуса прямо из списка: POST /status (или /close), тост с откатом. */
export function useQuickStatus() {
  const qc = useQueryClient();
  const [busyId, setBusyId] = useState<number | null>(null);

  const refresh = (d?: OrderDetail) => {
    if (d) qc.setQueryData(["order", d.id], d);
    for (const key of ["orders", "dashboard", "clients", "client", "flight", "flights"])
      qc.invalidateQueries({ queryKey: [key] });
  };

  const send = (id: number, next: OrderStatus) =>
    next === "closed"
      ? api.post<OrderDetail>(`/api/orders/${id}/close`, {})
      : api.post<OrderDetail>(`/api/orders/${id}/status`, { status: next });

  const change = (order: OrderListItem, next: OrderStatus) => {
    if (busyId !== null || next === order.status) return;
    const from = order.status;
    setBusyId(order.id);
    send(order.id, next)
      .then((d) => {
        refresh(d);
        toastSaved(
          () =>
            send(order.id, from)
              .then(refresh)
              .catch((e: ApiError) => toastError(e.message)),
          `#${order.id}: ${STATUS_LABEL[next]}`,
        );
      })
      .catch((e: ApiError) =>
        toastError(
          e.code === "commission_required"
            ? `#${order.id}: сначала заполните комиссию — без неё заказ не закрывается`
            : e.message,
        ),
      )
      .finally(() => setBusyId(null));
  };

  return { change, busyId };
}

/**
 * Маршрут в строке списка: кликом по сегменту двигается статус, не заходя в заказ.
 * Отменённые/возвращённые заказы не трогаем — их статусы живут в карточке.
 */
export function RouteStepperQuick({
  order,
  onSelect,
  busy,
}: {
  order: OrderListItem;
  onSelect: (order: OrderListItem, s: OrderStatus) => void;
  busy?: boolean;
}) {
  const [hover, setHover] = useState<number | null>(null);
  const idx = flowIndex(order.status);
  if (idx === -1) return <RouteStepperMini status={order.status} />;
  return (
    <div
      className={cx("flex w-32 shrink-0 gap-0.5", busy && "animate-pulse")}
      onMouseLeave={() => setHover(null)}
      // не даём клику уйти в строку-ссылку (таблица) или в <a> (мобильная карточка)
      onClick={(e) => {
        e.preventDefault();
        e.stopPropagation();
      }}
      onKeyDown={(e) => e.stopPropagation()}
    >
      {FLOW.map((s, i) => {
        const current = i === idx;
        // при наведении подсвечиваем, докуда дойдёт статус
        const filled = hover !== null ? i <= hover : i <= idx;
        return (
          <button
            key={s}
            type="button"
            disabled={busy || current}
            // только мышь: на тач-экране «наведение» залипало бы после тапа
            onPointerEnter={(e) => e.pointerType === "mouse" && setHover(i)}
            onFocus={(e) => e.target.matches(":focus-visible") && setHover(i)}
            onBlur={() => setHover(null)}
            onClick={() => onSelect(order, s)}
            title={
              current
                ? `Сейчас: ${STATUS_LABEL[s]}`
                : i < idx
                  ? `Откатить до «${STATUS_LABEL[s]}»`
                  : `Перевести в «${STATUS_LABEL[s]}»`
            }
            aria-label={STATUS_LABEL[s]}
            className="group flex h-5 flex-1 cursor-pointer items-center disabled:cursor-default"
          >
            <span
              className={cx(
                "h-2 w-full rounded-full transition-colors",
                filled
                  ? hover !== null
                    ? STATUS_BAR[FLOW[hover]]
                    : STATUS_BAR[order.status]
                  : "bg-line",
                current && hover === null && "ring-2 ring-accent/25",
              )}
            />
          </button>
        );
      })}
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
            title={
              i < idx ? `Откатить до «${STATUS_LABEL[s]}»` : `Перевести в «${STATUS_LABEL[s]}»`
            }
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
