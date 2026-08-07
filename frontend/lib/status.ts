import type { OrderStatus } from "./api-types";

export const FLOW: OrderStatus[] = [
  "purchased",
  "shipped",
  "at_warehouse",
  "in_flight",
  "delivered",
  "closed",
];

export const STATUS_LABEL: Record<OrderStatus, string> = {
  purchased: "Куплен",
  shipped: "Отправлен",
  at_warehouse: "Склад США",
  in_flight: "Рейс",
  delivered: "Доставлен",
  closed: "Закрыт",
  cancelled: "Отменён",
  refunded: "Возврат",
};

// Классы чипа статуса (фон/текст), light+dark.
export const STATUS_CHIP: Record<OrderStatus, string> = {
  purchased: "bg-zinc-500/12 text-zinc-600 dark:text-zinc-300",
  shipped: "bg-blue-500/12 text-blue-700 dark:text-blue-400",
  at_warehouse: "bg-cyan-500/12 text-cyan-700 dark:text-cyan-400",
  in_flight: "bg-violet-500/12 text-violet-700 dark:text-violet-400",
  delivered: "bg-amber-500/15 text-amber-700 dark:text-amber-400",
  closed: "bg-green-500/12 text-green-700 dark:text-green-400",
  cancelled: "bg-zinc-500/10 text-zinc-500 line-through",
  refunded: "bg-red-500/12 text-red-700 dark:text-red-400",
};

// Цвет заливки сегмента степпера.
export const STATUS_BAR: Record<string, string> = {
  purchased: "bg-zinc-400 dark:bg-zinc-500",
  shipped: "bg-blue-500",
  at_warehouse: "bg-cyan-500",
  in_flight: "bg-violet-500",
  delivered: "bg-amber-500",
  closed: "bg-green-500",
};

export function flowIndex(s: OrderStatus): number {
  return FLOW.indexOf(s);
}

export function isTerminal(s: OrderStatus): boolean {
  return s === "closed" || s === "cancelled" || s === "refunded";
}
