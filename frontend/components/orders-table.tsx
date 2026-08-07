"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import type { OrderListItem } from "@/lib/api-types";
import { fmtDate, fmtMoney } from "@/lib/format";
import { NoCommissionBadge, StatusBadge } from "./status-badge";
import { RouteStepperMini } from "./route-stepper";
import { cx } from "./ui";

export function OrdersTableHead({ showClient }: { showClient?: boolean }) {
  return (
    <thead>
      <tr className="border-b border-line text-left text-[11.5px] tracking-wide text-muted uppercase">
        <th className="px-3 py-2 font-medium">Заказ</th>
        {showClient && <th className="px-3 py-2 font-medium">Клиент</th>}
        <th className="px-3 py-2 font-medium">Статус</th>
        <th className="px-3 py-2 text-right font-medium">Комиссия</th>
        <th className="px-3 py-2 text-right font-medium">Обещано</th>
        <th className="px-3 py-2 text-right font-medium">Остаток</th>
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
            className="text-[13px] hover:text-accent hover:underline"
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
      <td className="px-3 py-2 text-right font-mono text-[12.5px] tnum">
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
          <span className="shrink-0 font-mono text-[13px] tnum">
            {order.due_usd === null ? "" : fmtMoney(order.due_usd)}
          </span>
        </div>
        <div className="truncate text-[12.5px] text-muted">
          {showClient && <>{order.client_name} · </>}
          {order.store}
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
  return (
    <>
      <div className="hidden overflow-x-auto sm:block">
        <table className="w-full min-w-[640px]">
          <OrdersTableHead showClient={showClient} />
          <tbody>
            {orders.map((o) => (
              <OrderRow key={o.id} order={o} showClient={showClient} />
            ))}
          </tbody>
        </table>
      </div>
      <ul className="divide-y divide-line/60 sm:hidden">
        {orders.map((o) => (
          <OrderCard key={o.id} order={o} showClient={showClient} />
        ))}
      </ul>
    </>
  );
}
