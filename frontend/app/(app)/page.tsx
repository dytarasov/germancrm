"use client";

import Link from "next/link";
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "@/lib/api";
import type { Dashboard, LoginBan, OrderListItem } from "@/lib/api-types";
import { fmtDateTime, fmtMoney, plural } from "@/lib/format";
import { STATUS_BAR, STATUS_LABEL } from "@/lib/status";
import { Button, Card, EmptyState, cx } from "@/components/ui";
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

type StageKey = "purchased" | "shipped" | "at_warehouse" | "in_flight" | "delivered";
type Filter = StageKey | "no_commission" | "overdue" | null;

const STAGES: StageKey[] = ["purchased", "shipped", "at_warehouse", "in_flight", "delivered"];

// узкая карточка этапа на телефоне: «Получено в США» обрезалось до «Получено в …»
const STAGE_SHORT: Partial<Record<StageKey, string>> = { at_warehouse: "В США" };

const FILTER_TITLE: Record<Exclude<Filter, null>, string> = {
  ...STATUS_LABEL,
  no_commission: "Без комиссии",
  overdue: "Опаздывают",
};

function matchesFilter(o: OrderListItem, f: Filter): boolean {
  if (f === null) return true;
  if (f === "no_commission") return o.commission_usd === null;
  if (f === "overdue") return o.is_overdue;
  return o.status === f;
}

/** Этапы маршрута: сколько заказов на каждом и на какую сумму закупки; тап — фильтр. */
function Pipeline({
  orders,
  filter,
  onFilter,
}: {
  orders: OrderListItem[];
  filter: Filter;
  onFilter: (f: Filter) => void;
}) {
  return (
    // телефон: этапы листаются пальцем вбок; от sm — сеткой в ряд
    <div className="-mx-4 flex snap-x snap-mandatory gap-2 overflow-x-auto px-4 pb-1 [scrollbar-width:none] sm:mx-0 sm:grid sm:grid-cols-5 sm:overflow-visible sm:px-0 sm:pb-0 [&::-webkit-scrollbar]:hidden">
      {STAGES.map((s) => {
        const list = orders.filter((o) => o.status === s);
        const sum = list.reduce((acc, o) => acc + parseFloat(o.purchase_price_usd), 0);
        const active = filter === s;
        return (
          <button
            key={s}
            type="button"
            aria-pressed={active}
            title={STATUS_LABEL[s]}
            onClick={() => onFilter(active ? null : s)}
            className={cx(
              "w-[7.25rem] shrink-0 snap-start rounded-lg border bg-surface p-3 text-left transition duration-150 ease-out active:scale-[0.97] sm:w-auto",
              active
                ? "border-accent ring-3 ring-accent-soft"
                : "border-line hover:border-muted/40",
            )}
          >
            <span className={cx("block h-1 rounded-full", STATUS_BAR[s])} />
            <span className="mt-2.5 block text-[22px] leading-none font-semibold tracking-tight tnum">
              {list.length}
            </span>
            <span className="mt-1 block truncate text-[12px] font-medium text-muted">
              {STAGE_SHORT[s] ?? STATUS_LABEL[s]}
            </span>
            <span className="block text-[11.5px] text-muted tnum">{fmtMoney(sum)}</span>
          </button>
        );
      })}
    </div>
  );
}

function AlertChip({
  children,
  active,
  onClick,
  href,
  tone = "amber",
}: {
  children: React.ReactNode;
  active?: boolean;
  onClick?: () => void;
  href?: string;
  tone?: "amber" | "red" | "green";
}) {
  const cls = cx(
    "inline-flex h-8 items-center gap-1.5 rounded-full px-3 text-[12.5px] font-medium whitespace-nowrap transition duration-150 ease-out active:scale-[0.97]",
    tone === "amber" && "bg-amber-500/12 text-amber-700 dark:text-amber-400",
    tone === "red" && "bg-red-500/10 text-red-700 dark:text-red-400",
    tone === "green" && "bg-green-500/10 text-green-700 dark:text-green-400",
    active && "ring-2 ring-current/30",
  );
  if (href)
    return (
      <Link href={href} className={cls}>
        {children}
      </Link>
    );
  if (!onClick) return <span className={cls}>{children}</span>;
  return (
    <button type="button" aria-pressed={active} onClick={onClick} className={cls}>
      {children}
    </button>
  );
}

type MailAlert = { text: string; href: string; kind: "red" | "amber" };

/** Сигналы почты: красные (CRM не видит письма) — полосой сверху,
 * жёлтые (ручной разбор, LLM) — плашками в строке задач рядом с «без комиссии». */
function mailAlerts(d: Dashboard): MailAlert[] {
  const m = d.mail;
  const banners: MailAlert[] = [];
  if (m.needs_reauth)
    banners.push({ text: "Gmail требует повторной авторизации", href: "/settings", kind: "red" });
  else if (m.configured && m.gmail_connected && !m.worker_ok)
    banners.push({
      text: `Почта не читается${m.last_success_at ? ` с ${fmtDateTime(m.last_success_at)}` : ""}`,
      href: "/mail",
      kind: "red",
    });
  if (m.llm_degraded)
    banners.push({ text: "LLM недоступен — письма ждут", href: "/mail", kind: "amber" });
  if (m.poison + m.manual_review > 0)
    banners.push({
      text: `${m.poison + m.manual_review} ${plural(m.poison + m.manual_review, "письмо", "письма", "писем")} на ручной разбор`,
      href: "/mail",
      kind: "amber",
    });
  return banners;
}

function MailBanners({ alerts }: { alerts: MailAlert[] }) {
  const banners = alerts.filter((a) => a.kind === "red");
  if (banners.length === 0) return null;
  return (
    <div className="space-y-2">
      {banners.map((b, i) => (
        <Link
          key={i}
          href={b.href}
          className={
            "block rounded-lg border border-red-500/30 bg-red-500/8 px-3.5 py-2.5 text-[13px] font-medium text-red-700 dark:text-red-400"
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
  const [filter, setFilter] = useState<Filter>(null);
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
  const active = activeOrders ?? [];
  const newestFirst = [...active].sort((a, b) => b.id - a.id);
  const inProgress = [...newestFirst.slice(0, 6), ...newestFirst.slice(6).sort(byUrgency)];
  const shown = inProgress.filter((o) => matchesFilter(o, filter));

  const noCom = data.attention.no_commission.length;
  const overdue = data.attention.overdue.length;
  const unmatched = data.attention.unmatched_tracks.length;
  const mail = mailAlerts(data);
  const toggle = (f: Exclude<Filter, null>) => setFilter((cur) => (cur === f ? null : f));

  return (
    <div className="space-y-4">
      <div>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h1 className="text-[17px] font-semibold tracking-tight">Дашборд</h1>
          <Button variant="primary" onClick={() => setNewOrder(true)}>
            Новый заказ
          </Button>
        </div>
        <div className="mt-1.5 flex flex-wrap gap-x-5 gap-y-0.5 text-[13px] text-muted">
          <span>
            В работе <b className="font-semibold text-ink tnum">{data.orders_in_progress}</b>
          </span>
          <span>
            Долг клиентов{" "}
            <b className="font-semibold text-amber-700 tnum dark:text-amber-400">
              {fmtMoney(data.clients_debt_usd)}
            </b>
          </span>
          <span
            title={`комиссии ${fmtMoney(data.month_commissions_usd)} − рейсы ${fmtMoney(
              data.month_flights_cost_usd,
            )}`}
          >
            Прибыль за месяц{" "}
            <b className="font-semibold text-ink tnum">{fmtMoney(data.month_profit_usd)}</b>
          </span>
        </div>
      </div>

      <SecurityBanners />
      <MailBanners alerts={mail} />

      <Pipeline orders={active} filter={filter} onFilter={setFilter} />

      <div className="flex flex-wrap gap-1.5">
        {mail
          .filter((a) => a.kind === "amber")
          .map((a) => (
            <AlertChip key={a.text} href={a.href}>
              {a.text} →
            </AlertChip>
          ))}
        {noCom > 0 && (
          <AlertChip active={filter === "no_commission"} onClick={() => toggle("no_commission")}>
            {noCom} без комиссии
          </AlertChip>
        )}
        {overdue > 0 && (
          <AlertChip tone="red" active={filter === "overdue"} onClick={() => toggle("overdue")}>
            {overdue} {plural(overdue, "опаздывает", "опаздывают", "опаздывают")}
          </AlertChip>
        )}
        {unmatched > 0 ? (
          <AlertChip href="/tracks">
            {unmatched} {plural(unmatched, "трек", "трека", "треков")} без заказа →
          </AlertChip>
        ) : (
          <AlertChip tone="green">✓ треки привязаны</AlertChip>
        )}
        {noCom === 0 && overdue === 0 && <AlertChip tone="green">✓ сроки и комиссии в порядке</AlertChip>}
      </div>

      <Card>
        <div className="flex items-center justify-between border-b border-line px-3 py-2.5">
          <h2 className="text-[13px] font-semibold">
            {filter ? FILTER_TITLE[filter] : "Заказы в работе"}
            <span className="ml-2 font-normal text-muted tnum">{shown.length}</span>
          </h2>
          {filter ? (
            <button
              type="button"
              onClick={() => setFilter(null)}
              className="text-[12.5px] font-medium text-accent hover:underline"
            >
              Показать все
            </button>
          ) : (
            <Link href="/orders" className="text-[12.5px] font-medium text-accent hover:underline">
              Все заказы →
            </Link>
          )}
        </div>
        {shown.length === 0 ? (
          <EmptyState
            title={filter ? "Здесь пусто" : "Активных заказов нет"}
            hint={filter ? undefined : "Новый заказ появится здесь в момент покупки."}
          />
        ) : (
          <OrdersTable orders={shown} showClient />
        )}
      </Card>

      <NewOrderModal open={newOrder} onClose={() => setNewOrder(false)} />
    </div>
  );
}
