"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import type { OrderListItem } from "@/lib/api-types";
import { fmtDate, fmtMoney } from "@/lib/format";
import { flowIndex } from "@/lib/status";
import { NoCommissionBadge, StatusBadge } from "./status-badge";
import { RouteStepperMini } from "./route-stepper";
import { cx } from "./ui";

export type OrderSortKey = "client" | "status" | "commission" | "promised" | "due";
export type OrderSort = { key: OrderSortKey; dir: 1 | -1 } | null;

// Позиция статуса для сортировки: пайплайн по порядку, терминальные — в конец.
function statusRank(o: OrderListItem): number {
  const i = flowIndex(o.status);
  if (i >= 0) return i;
  return o.status === "cancelled" ? 6 : 7; // refunded — последним
}

const SORT_VALUE: Record<OrderSortKey, (o: OrderListItem) => string | number | null> = {
  client: (o) => o.client_name,
  status: statusRank,
  commission: (o) => (o.commission_usd === null ? null : parseFloat(o.commission_usd)),
  promised: (o) => o.promised_date,
  due: (o) => (o.due_usd === null ? null : parseFloat(o.due_usd)),
};

export function sortOrders(orders: OrderListItem[], sort: OrderSort): OrderListItem[] {
  if (!sort) return orders;
  const val = SORT_VALUE[sort.key];
  return [...orders].sort((a, b) => {
    const va = val(a);
    const vb = val(b);
    if (va === null && vb === null) return 0;
    if (va === null) return 1; // пустые значения всегда в конце
    if (vb === null) return -1;
    const c =
      typeof va === "string"
        ? va.localeCompare(vb as string, "ru")
        : (va as number) - (vb as number);
    return c * sort.dir;
  });
}

function SortableTh({
  label,
  k,
  sort,
  onSort,
  right,
}: {
  label: string;
  k: OrderSortKey;
  sort: OrderSort;
  onSort?: (k: OrderSortKey) => void;
  right?: boolean;
}) {
  const cls = cx("px-3 py-2 font-medium", right && "text-right");
  if (!onSort) return <th className={cls}>{label}</th>;
  const active = sort?.key === k;
  return (
    <th className={cls} aria-sort={active ? (sort.dir === 1 ? "ascending" : "descending") : "none"}>
      <button
        type="button"
        onClick={() => onSort(k)}
        className={cx(
          "cursor-pointer uppercase tracking-wide hover:text-ink",
          active && "text-accent",
        )}
        title="Сортировать"
      >
        {label}
        {active && <span className="ml-0.5">{sort.dir === 1 ? "↑" : "↓"}</span>}
      </button>
    </th>
  );
}

export function OrdersTableHead({
  showClient,
  sort,
  onSort,
}: {
  showClient?: boolean;
  sort?: OrderSort;
  onSort?: (k: OrderSortKey) => void;
}) {
  const s = sort ?? null;
  return (
    <thead>
      <tr className="border-b border-line text-left text-[11.5px] tracking-wide text-muted uppercase">
        <th className="px-3 py-2 font-medium">Заказ</th>
        {showClient && <SortableTh label="Клиент" k="client" sort={s} onSort={onSort} />}
        <SortableTh label="Статус" k="status" sort={s} onSort={onSort} />
        <SortableTh label="Комиссия" k="commission" sort={s} onSort={onSort} right />
        <SortableTh label="Обещано" k="promised" sort={s} onSort={onSort} right />
        <SortableTh label="Остаток" k="due" sort={s} onSort={onSort} right />
      </tr>
    </thead>
  );
}

export function OrderRow({ order, showClient }: { order: OrderListItem; showClient?: boolean }) {
  const router = useRouter();
  const go = () => router.push(`/orders/${order.id}`);
  return (
    <tr
      tabIndex={0}
      role="link"
      aria-label={`Заказ #${order.id}: ${order.items}`}
      onClick={go}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          go();
        }
      }}
      className="cursor-pointer border-b border-line/60 transition-colors last:border-0 hover:bg-surface2/60"
    >
      <td className="max-w-70 px-3 py-2">
        <div className="truncate text-[13px] font-medium">{order.items}</div>
        <div className="truncate text-[12px] text-muted">
          {order.store}
          {order.suborders_count > 1 && (
            <span
              className="ml-1.5 rounded bg-accent-soft px-1 font-mono text-[11px] font-semibold text-accent"
              title={`Корзина из ${order.suborders_count} подзаказов`}
            >
              ×{order.suborders_count}
            </span>
          )}
          {order.store_order_number && (
            <span className="ml-1.5 font-mono text-[11.5px]">{order.store_order_number}</span>
          )}
          {order.tracks_count > 0 && <span className="ml-1.5">· {order.tracks_count} трек.</span>}
        </div>
      </td>
      {showClient && (
        <td className="px-3 py-2">
          <Link
            href={`/clients/${order.client_id}`}
            onClick={(e) => e.stopPropagation()}
            className="text-[13px] font-medium text-accent hover:underline"
          >
            {order.client_name}
          </Link>
        </td>
      )}
      <td className="px-3 py-2">
        <div className="flex items-center gap-2.5">
          <RouteStepperMini status={order.status} />
          <StatusBadge status={order.status} />
        </div>
      </td>
      <td className="px-3 py-2 text-right font-mono text-[12.5px] tnum">
        {order.commission_usd === null ? <NoCommissionBadge /> : fmtMoney(order.commission_usd)}
      </td>
      <td
        className={cx(
          "px-3 py-2 text-right text-[12.5px]",
          order.is_overdue ? "font-semibold text-red-600 dark:text-red-400" : "text-muted",
        )}
      >
        {fmtDate(order.promised_date)}
      </td>
      <td
        className={cx(
          "px-3 py-2 text-right font-mono text-[12.5px] tnum",
          order.due_usd !== null && parseFloat(order.due_usd) > 0
            ? "font-semibold text-amber-700 dark:text-amber-400"
            : "text-muted",
        )}
      >
        {order.due_usd === null ? "—" : fmtMoney(order.due_usd)}
      </td>
    </tr>
  );
}

/** Карточный вид строки заказа для узких экранов (<sm). */
export function OrderCard({ order, showClient }: { order: OrderListItem; showClient?: boolean }) {
  return (
    <li>
      <Link href={`/orders/${order.id}`} className="block px-3 py-3 active:bg-surface2/60">
        <div className="flex items-baseline justify-between gap-2">
          <span className="min-w-0 truncate text-[14px] font-medium">{order.items}</span>
          <span
            className={cx(
              "shrink-0 font-mono text-[13px] tnum",
              order.due_usd !== null && parseFloat(order.due_usd) > 0
                ? "font-semibold text-amber-700 dark:text-amber-400"
                : "text-muted",
            )}
          >
            {order.due_usd === null ? "" : fmtMoney(order.due_usd)}
          </span>
        </div>
        <div className="truncate text-[12.5px] text-muted">
          {showClient && <>{order.client_name} · </>}
          {order.store}
          {order.suborders_count > 1 && (
            <span className="ml-1 rounded bg-accent-soft px-1 font-mono text-[11px] font-semibold text-accent">
              ×{order.suborders_count}
            </span>
          )}
          {order.store_order_number && (
            <>
              {" "}· <span className="font-mono text-[11.5px]">{order.store_order_number}</span>
            </>
          )}
          {order.tracks_count > 0 && <> · {order.tracks_count} трек.</>}
        </div>
        <div className="mt-2 flex flex-wrap items-center gap-x-2.5 gap-y-1">
          <RouteStepperMini status={order.status} />
          <StatusBadge status={order.status} />
          {order.commission_usd === null ? (
            <NoCommissionBadge />
          ) : (
            <span className="font-mono text-[12px] text-muted tnum">
              ком. {fmtMoney(order.commission_usd)}
            </span>
          )}
          <span
            className={cx(
              "ml-auto text-[12px]",
              order.is_overdue ? "font-semibold text-red-600 dark:text-red-400" : "text-muted",
            )}
          >
            {fmtDate(order.promised_date)}
          </span>
        </div>
      </Link>
    </li>
  );
}

export function OrdersTable({
  orders,
  showClient,
}: {
  orders: OrderListItem[];
  showClient?: boolean;
}) {
  // Клик по заголовку: по возрастанию → по убыванию → исходный порядок.
  const [sort, setSort] = useState<OrderSort>(null);
  const toggleSort = (k: OrderSortKey) =>
    setSort((s) => (s?.key !== k ? { key: k, dir: 1 } : s.dir === 1 ? { key: k, dir: -1 } : null));
  const sorted = useMemo(() => sortOrders(orders, sort), [orders, sort]);
  return (
    <>
      <div className="hidden overflow-x-auto sm:block">
        <table className="w-full min-w-[640px]">
          <OrdersTableHead showClient={showClient} sort={sort} onSort={toggleSort} />
          <tbody>
            {sorted.map((o) => (
              <OrderRow key={o.id} order={o} showClient={showClient} />
            ))}
          </tbody>
        </table>
      </div>
      <ul className="divide-y divide-line/60 sm:hidden">
        {sorted.map((o) => (
          <OrderCard key={o.id} order={o} showClient={showClient} />
        ))}
      </ul>
    </>
  );
}
