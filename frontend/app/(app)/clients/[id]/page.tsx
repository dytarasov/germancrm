"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "@/lib/api";
import type { ClientDetail, OrderListItem } from "@/lib/api-types";
import { fmtDateFull, fmtMoney, telegramLink } from "@/lib/format";
import { Button, Card, cx } from "@/components/ui";
import { InlineField } from "@/components/inline-field";
import { NoCommissionBadge, StatusBadge } from "@/components/status-badge";
import { NewOrderModal } from "@/components/new-order-modal";
import { toastError, toastSaved } from "@/components/toasts";

const num = (v: string | null) => (v === null ? 0 : parseFloat(v));

/** Свежие покупки сверху; отменённые не входят в итоги. */
function totals(orders: OrderListItem[]) {
  const live = orders.filter((o) => o.status !== "cancelled");
  return {
    purchase: live.reduce((s, o) => s + num(o.purchase_price_usd), 0),
    commission: live.reduce((s, o) => s + num(o.commission_usd), 0),
    paid: orders.reduce((s, o) => s + num(o.paid_usd), 0),
    noCommission: live.filter((o) => o.commission_usd === null).length,
  };
}

function DueCell({ o }: { o: OrderListItem }) {
  const due = o.due_usd === null ? null : parseFloat(o.due_usd);
  return (
    <span
      className={cx(
        "font-mono tnum",
        due !== null && due > 0 ? "font-semibold text-amber-700 dark:text-amber-400" : "text-muted",
      )}
    >
      {due === null ? "—" : fmtMoney(due)}
    </span>
  );
}

/** Упрощённый вид заказов клиента: дата, сайт, закупка и деньги — без логистики. */
function ClientOrders({ orders }: { orders: OrderListItem[] }) {
  const router = useRouter();
  const sorted = [...orders].sort(
    (a, b) => b.purchased_on.localeCompare(a.purchased_on) || b.id - a.id,
  );
  const t = totals(orders);
  const muted = (o: OrderListItem) => o.status === "cancelled" && "opacity-50";

  return (
    <>
      <div className="hidden overflow-x-auto sm:block">
        <table className="w-full min-w-[720px]">
          <thead>
            <tr className="border-b border-line text-left text-[11.5px] tracking-wide text-muted uppercase">
              <th className="px-3 py-2 font-medium">Дата</th>
              <th className="px-3 py-2 font-medium">Сайт</th>
              <th className="px-3 py-2 text-right font-medium">Закупка</th>
              <th className="px-3 py-2 text-right font-medium">Комиссия</th>
              <th className="px-3 py-2 text-right font-medium">Внесено</th>
              <th className="px-3 py-2 text-right font-medium">Остаток</th>
              <th className="px-3 py-2 font-medium">Статус</th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((o) => (
              <tr
                key={o.id}
                tabIndex={0}
                role="link"
                aria-label={`Заказ #${o.id}: ${o.items}`}
                onClick={() => router.push(`/orders/${o.id}`)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault();
                    router.push(`/orders/${o.id}`);
                  }
                }}
                className={cx(
                  "cursor-pointer border-b border-line/60 text-[13px] last:border-0 hover:bg-surface2/60",
                  muted(o),
                )}
              >
                <td className="px-3 py-2 whitespace-nowrap">{fmtDateFull(o.purchased_on)}</td>
                <td className="max-w-64 px-3 py-2">
                  <div className="truncate font-medium">
                    {o.store}
                    {o.suborders_count > 1 && (
                      <span className="ml-1.5 rounded bg-accent-soft px-1 font-mono text-[11px] font-semibold text-accent">
                        ×{o.suborders_count}
                      </span>
                    )}
                  </div>
                  <div className="truncate text-[12px] text-muted">{o.items}</div>
                </td>
                <td className="px-3 py-2 text-right font-mono tnum">
                  {fmtMoney(o.purchase_price_usd)}
                </td>
                <td className="px-3 py-2 text-right font-mono tnum">
                  {o.commission_usd === null ? <NoCommissionBadge /> : fmtMoney(o.commission_usd)}
                </td>
                <td className="px-3 py-2 text-right font-mono tnum">{fmtMoney(o.paid_usd)}</td>
                <td className="px-3 py-2 text-right">
                  <DueCell o={o} />
                </td>
                <td className="px-3 py-2">
                  <StatusBadge status={o.status} />
                </td>
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr className="border-t border-line bg-surface2/50 text-[13px] font-semibold">
              <td className="px-3 py-2" colSpan={2}>
                Итого
                <span className="ml-2 text-[12px] font-normal text-muted">без отменённых</span>
              </td>
              <td className="px-3 py-2 text-right font-mono tnum">{fmtMoney(t.purchase)}</td>
              <td className="px-3 py-2 text-right font-mono tnum">{fmtMoney(t.commission)}</td>
              <td className="px-3 py-2 text-right font-mono tnum">{fmtMoney(t.paid)}</td>
              <td colSpan={2} />
            </tr>
          </tfoot>
        </table>
      </div>

      <ul className="divide-y divide-line/60 sm:hidden">
        {sorted.map((o) => (
          <li key={o.id} className={cx(muted(o))}>
            <Link href={`/orders/${o.id}`} className="block px-3 py-3 active:bg-surface2/60">
              <div className="flex items-baseline justify-between gap-2">
                <span className="min-w-0 truncate text-[14px] font-medium">
                  {o.store}
                  {o.suborders_count > 1 && (
                    <span className="ml-1 rounded bg-accent-soft px-1 font-mono text-[11px] font-semibold text-accent">
                      ×{o.suborders_count}
                    </span>
                  )}
                </span>
                <span className="shrink-0 text-[12.5px] text-muted">
                  {fmtDateFull(o.purchased_on)}
                </span>
              </div>
              <div className="truncate text-[12.5px] text-muted">{o.items}</div>
              <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-[12px]">
                <span className="font-mono tnum">зак. {fmtMoney(o.purchase_price_usd)}</span>
                {o.commission_usd === null ? (
                  <NoCommissionBadge />
                ) : (
                  <span className="font-mono text-muted tnum">
                    ком. {fmtMoney(o.commission_usd)}
                  </span>
                )}
                <span className="font-mono text-muted tnum">внес. {fmtMoney(o.paid_usd)}</span>
                <span className="ml-auto">
                  <DueCell o={o} />
                </span>
              </div>
            </Link>
          </li>
        ))}
      </ul>
    </>
  );
}

function MoneyRow({
  label,
  value,
  sub,
  className,
}: {
  label: string;
  value: string;
  sub?: string;
  className?: string;
}) {
  return (
    <div>
      <div className="flex items-baseline justify-between gap-3">
        <span className="text-[12.5px] text-muted">{label}</span>
        <span className={cx("font-mono text-[15px] font-semibold tnum", className)}>{value}</span>
      </div>
      {sub && <div className="text-right text-[11.5px] text-muted">{sub}</div>}
    </div>
  );
}

export default function ClientPage() {
  const { id } = useParams<{ id: string }>();
  const clientId = Number(id);
  const qc = useQueryClient();
  const router = useRouter();
  const [newOrder, setNewOrder] = useState(false);

  const { data, isLoading } = useQuery({
    queryKey: ["client", clientId],
    queryFn: () => api.get<ClientDetail>(`/api/clients/${clientId}`),
  });

  const patch = useMutation<unknown, ApiError, Record<string, unknown>>({
    mutationFn: (body) => api.patch(`/api/clients/${clientId}`, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["client", clientId] });
      qc.invalidateQueries({ queryKey: ["clients"] });
    },
    onError: (e) => toastError(e.message),
  });

  if (isLoading || !data)
    return <p className="py-16 text-center text-[13px] text-muted">Загрузка…</p>;

  const c = data.client;
  const tg = telegramLink(c.telegram_url);
  const t = totals(data.orders);
  // Бэкенд удаляет только клиента без заказов (иначе 409) — кнопку при заказах гасим заранее.
  const hasOrders = data.orders.length > 0;
  const remove = () => {
    if (!window.confirm(`Удалить клиента «${c.name}»? Вернуть его будет нельзя.`)) return;
    api
      .del(`/api/clients/${clientId}`)
      .then(() => {
        toastSaved(undefined, "Клиент удалён");
        qc.invalidateQueries({ queryKey: ["clients"] });
        router.push("/clients");
      })
      .catch((err) => toastError(err.message));
  };
  const save = (field: string, v: string | null, old: string | null) =>
    patch.mutate(
      { [field]: v },
      { onSuccess: () => toastSaved(() => patch.mutate({ [field]: old })) },
    );

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-[17px] font-semibold tracking-tight">{c.name}</h1>
        {tg && (
          <a
            href={tg.href}
            target="_blank"
            rel="noopener noreferrer"
            className="text-[13px] text-accent hover:underline"
          >
            {tg.label} · написать в Telegram →
          </a>
        )}
        <Button variant="primary" className="ml-auto" onClick={() => setNewOrder(true)}>
          Новый заказ
        </Button>
      </div>

      <div className="grid grid-cols-1 gap-3 lg:grid-cols-3">
        <Card className="grid grid-cols-1 gap-x-4 gap-y-3 p-4 sm:grid-cols-2 lg:col-span-2">
          <InlineField label="Имя" value={c.name} onSave={(v) => v && save("name", v, c.name)} />
          <InlineField
            label="Telegram"
            value={c.telegram_url}
            placeholder="@ник или https://t.me/…"
            onSave={(v) => save("telegram_url", v, c.telegram_url)}
          />
          <InlineField
            label="Контакты"
            value={c.contacts}
            onSave={(v) => save("contacts", v, c.contacts)}
          />
          <InlineField label="Заметка" value={c.note} onSave={(v) => save("note", v, c.note)} />
        </Card>
        <Card className="space-y-2.5 p-4">
          <MoneyRow
            label="Внесено всего"
            value={fmtMoney(t.paid)}
            sub={`за закупки на ${fmtMoney(t.purchase)}`}
          />
          <MoneyRow
            label="Комиссионная часть"
            value={fmtMoney(t.commission)}
            sub={t.noCommission > 0 ? `ещё ${t.noCommission} зак. без комиссии` : undefined}
          />
          <div className="border-t border-line pt-2.5">
            <MoneyRow label="Долг" value={fmtMoney(data.debt_usd)} />
          </div>
          <MoneyRow
            label="Заработано (закрытые)"
            value={fmtMoney(data.earned_usd)}
            className="text-green-600 dark:text-green-400"
          />
        </Card>
      </div>

      <Card>
        {data.orders.length === 0 ? (
          <p className="py-8 text-center text-[13px] text-muted">Заказов пока нет</p>
        ) : (
          <ClientOrders orders={data.orders} />
        )}
      </Card>

      <div className="flex flex-wrap items-center justify-end gap-3">
        {hasOrders && (
          <span className="text-[12px] text-muted">
            У клиента есть заказы — удалить нельзя
          </span>
        )}
        <Button variant="danger" disabled={hasOrders} onClick={remove}>
          Удалить клиента
        </Button>
      </div>

      <NewOrderModal
        open={newOrder}
        onClose={() => setNewOrder(false)}
        defaultClientId={clientId}
      />
    </div>
  );
}
