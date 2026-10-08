"use client";

import Link from "next/link";
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "@/lib/api";
import type { Dashboard, LoginBan, OrderListItem } from "@/lib/api-types";
import { fmtDate, fmtDateTime, fmtMoney } from "@/lib/format";
import { Button, Card, EmptyState } from "@/components/ui";
import { NoCommissionBadge } from "@/components/status-badge";
import { OrdersTable } from "@/components/orders-table";
import { NewOrderModal } from "@/components/new-order-modal";
import { toastError, toastSaved } from "@/components/toasts";

// Срочное сверху: просроченные, затем по ближайшему обещанному сроку, затем свежие.
function byUrgency(a: OrderListItem, b: OrderListItem): number {
  if (a.is_overdue !== b.is_overdue) return a.is_overdue ? -1 : 1;
  if (a.promised_date && b.promised_date && a.promised_date !== b.promised_date)
    return a.promised_date < b.promised_date ? -1 : 1;
  if (!!a.promised_date !== !!b.promised_date) return a.promised_date ? -1 : 1;
  return b.id - a.id;
}

function StatTile({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <Card className="p-4">
      <div className="text-[12px] font-medium text-muted">{label}</div>
      <div className="mt-1 font-mono text-[26px] leading-none font-semibold tracking-tight tnum">
        {value}
      </div>
      {sub && <div className="mt-1.5 text-[11.5px] text-muted">{sub}</div>}
    </Card>
  );
}

function MiniOrderList({ orders, accent }: { orders: OrderListItem[]; accent: "amber" | "red" }) {
  if (orders.length === 0)
    return <p className="px-1 py-3 text-[12.5px] text-muted">Всё в порядке</p>;
  return (
    <ul className="divide-y divide-line/60">
      {orders.slice(0, 6).map((o) => (
        <li key={o.id}>
          <Link
            href={`/orders/${o.id}`}
            className="flex items-baseline justify-between gap-3 px-1 py-2 hover:bg-surface2/50"
          >
            <span className="min-w-0">
              <span className="block truncate text-[13px] font-medium">{o.items}</span>
              <span className="block truncate text-[12px] text-muted">
                {o.client_name} · {o.store}
              </span>
            </span>
            {accent === "amber" ? (
              <NoCommissionBadge />
            ) : (
              <span className="shrink-0 text-[12px] font-semibold text-red-600 dark:text-red-400">
                {fmtDate(o.promised_date)}
              </span>
            )}
          </Link>
        </li>
      ))}
    </ul>
  );
}

function MailBanners({ d }: { d: Dashboard }) {
  const m = d.mail;
  const banners: { text: string; href: string; kind: "red" | "amber" }[] = [];
  if (m.needs_reauth)
    banners.push({ text: "Gmail требует повторной авторизации", href: "/settings", kind: "red" });
  else if (m.configured && m.gmail_connected && !m.worker_ok)
    banners.push({
      text: `Почта не читается${m.last_success_at ? ` с ${fmtDateTime(m.last_success_at)}` : ""}`,
      href: "/mail",
      kind: "red",
    });
  if (m.llm_degraded)
    banners.push({ text: "LLM недоступен — письма копятся в очереди", href: "/mail", kind: "amber" });
  if (m.poison + m.manual_review > 0)
    banners.push({
      text: `Писем ждёт ручного разбора: ${m.poison + m.manual_review}`,
      href: "/mail",
      kind: "amber",
    });
  if (banners.length === 0) return null;
  return (
    <div className="space-y-2">
      {banners.map((b, i) => (
        <Link
          key={i}
          href={b.href}
          className={
            "block rounded-lg border px-3.5 py-2.5 text-[13px] font-medium " +
            (b.kind === "red"
              ? "border-red-500/30 bg-red-500/8 text-red-700 dark:text-red-400"
              : "border-amber-500/30 bg-amber-500/8 text-amber-700 dark:text-amber-400")
          }
        >
          {b.text} →
        </Link>
      ))}
    </div>
  );
}

function SecurityBanners() {
  const qc = useQueryClient();
  const { data: bans } = useQuery({
    queryKey: ["security-bans"],
    queryFn: () => api.get<LoginBan[]>("/api/security/bans"),
    refetchInterval: 60_000,
  });
  const unban = useMutation<void, ApiError, string>({
    mutationFn: (ip) => api.del(`/api/security/bans/${ip}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["security-bans"] });
      toastSaved(undefined, "Бан снят");
    },
    onError: (e) => toastError(e.message),
  });

  const rows = (bans ?? []).filter((b) => b.fails > 0);
  if (rows.length === 0) return null;
  return (
    <div className="space-y-2">
      {rows.map((b) => {
        const banned = b.banned_until !== null && new Date(b.banned_until) > new Date();
        return (
          <div
            key={b.ip}
            className={
              "flex flex-wrap items-center gap-x-3 gap-y-1 rounded-lg border px-3.5 py-2.5 text-[13px] font-medium " +
              (banned
                ? "border-red-500/30 bg-red-500/8 text-red-700 dark:text-red-400"
                : "border-amber-500/30 bg-amber-500/8 text-amber-700 dark:text-amber-400")
            }
          >
            <span className="min-w-0">
              {banned
                ? `Попытка взлома: IP ${b.ip} перебирал пароль (${b.fails} промахов) — забанен до ${fmtDateTime(b.banned_until)}`
                : `С IP ${b.ip} было ${b.fails} неверных паролей (${fmtDateTime(b.last_fail_at)})`}
            </span>
            <Button
              variant="ghost"
              className="ml-auto h-7 shrink-0"
              onClick={() => unban.mutate(b.ip)}
              disabled={unban.isPending}
            >
              {banned ? "Снять бан" : "Сбросить счётчик"}
            </Button>
          </div>
        );
      })}
    </div>
  );
}

export default function DashboardPage() {
  const [newOrder, setNewOrder] = useState(false);
  const { data, isLoading } = useQuery({
    queryKey: ["dashboard"],
    queryFn: () => api.get<Dashboard>("/api/dashboard"),
    refetchInterval: 60_000,
  });
  const { data: activeOrders } = useQuery({
    queryKey: ["orders", { active: true }],
    queryFn: () => api.get<OrderListItem[]>("/api/orders?active=true"),
    refetchInterval: 60_000,
  });

  if (isLoading || !data)
    return <p className="py-16 text-center text-[13px] text-muted">Загрузка…</p>;

  // Сверху 6 последних созданных (новые первыми), остальные — по срочности.
  const newestFirst = [...(activeOrders ?? [])].sort((a, b) => b.id - a.id);
  const inProgress = [...newestFirst.slice(0, 6), ...newestFirst.slice(6).sort(byUrgency)];

  const noAttention =
    data.attention.no_commission.length === 0 &&
    data.attention.overdue.length === 0 &&
    data.attention.unmatched_tracks.length === 0;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-[17px] font-semibold tracking-tight">Дашборд</h1>
        <Button variant="primary" onClick={() => setNewOrder(true)}>
          Новый заказ
        </Button>
      </div>

      <SecurityBanners />
      <MailBanners d={data} />

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <StatTile label="Заказов в работе" value={String(data.orders_in_progress)} />
        <StatTile label="Долг клиентов" value={fmtMoney(data.clients_debt_usd)} />
        <StatTile
          label="Прибыль за месяц"
          value={fmtMoney(data.month_profit_usd)}
          sub={`комиссии ${fmtMoney(data.month_commissions_usd)} − рейсы ${fmtMoney(
            data.month_flights_cost_usd,
          )}`}
        />
      </div>

      {noAttention ? (
        <Card>
          <EmptyState
            title="Ничего не требует внимания"
            hint="Комиссии заполнены, сроки не горят, все треки привязаны."
          />
        </Card>
      ) : (
        <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
          <Card className="p-3">
            <h2 className="flex items-center justify-between px-1 text-[12.5px] font-semibold">
              Без комиссии
              <span className="text-muted">{data.attention.no_commission.length}</span>
            </h2>
            <MiniOrderList orders={data.attention.no_commission} accent="amber" />
          </Card>
          <Card className="p-3">
            <h2 className="flex items-center justify-between px-1 text-[12.5px] font-semibold">
              Опаздывают
              <span className="text-muted">{data.attention.overdue.length}</span>
            </h2>
            <MiniOrderList orders={data.attention.overdue} accent="red" />
          </Card>
          <Card className="p-3">
            <h2 className="flex items-center justify-between px-1 text-[12.5px] font-semibold">
              Непривязанные треки
              <span className="text-muted">{data.attention.unmatched_tracks.length}</span>
            </h2>
            {data.attention.unmatched_tracks.length === 0 ? (
              <p className="px-1 py-3 text-[12.5px] text-muted">Всё привязано</p>
            ) : (
              <ul className="divide-y divide-line/60">
                {data.attention.unmatched_tracks.slice(0, 6).map((t) => (
                  <li key={t.id}>
                    <Link
                      href="/tracks"
                      className="flex items-center justify-between gap-2 px-1 py-2 hover:bg-surface2/50"
                    >
                      <span className="truncate font-mono text-[12.5px]">{t.tracking_number}</span>
                      <span className="shrink-0 text-[11.5px] text-muted">
                        {t.carrier ?? "—"}
                      </span>
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </div>
      )}

      <Card>
        <div className="flex items-center justify-between border-b border-line px-3 py-2.5">
          <h2 className="text-[12.5px] font-semibold">
            Заказы в работе
            <span className="ml-2 font-normal text-muted">{inProgress.length}</span>
          </h2>
          <Link href="/orders" className="text-[12.5px] font-medium text-accent hover:underline">
            Все заказы →
          </Link>
        </div>
        {inProgress.length === 0 ? (
          <EmptyState
            title="Активных заказов нет"
            hint="Новый заказ появится здесь в момент покупки."
          />
        ) : (
          <OrdersTable orders={inProgress} showClient />
        )}
      </Card>

      <NewOrderModal open={newOrder} onClose={() => setNewOrder(false)} />
    </div>
  );
}
