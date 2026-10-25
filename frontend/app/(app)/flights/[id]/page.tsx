"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "@/lib/api";
import type { FlightDetail, OrderListItem } from "@/lib/api-types";
import { fmtDateFull, fmtMoney } from "@/lib/format";
import { Button, Card, Input, cx } from "@/components/ui";
import { EditFlightModal } from "@/components/flight-edit-modal";
import { StatusBadge } from "@/components/status-badge";
import { toastError, toastSaved } from "@/components/toasts";

const kg = (o: OrderListItem) => (o.weight_kg ? parseFloat(o.weight_kg) : 0);

const byClient = (a: OrderListItem, b: OrderListItem) =>
  a.client_name.localeCompare(b.client_name, "ru") || a.id - b.id;

function matches(o: OrderListItem, q: string): boolean {
  if (!q) return true;
  const hay = `${o.client_name} ${o.items} ${o.store} ${o.store_order_number ?? ""} #${o.id}`;
  return hay.toLowerCase().includes(q);
}

/**
 * Страница рейса: что в нём едет — галками.
 * Сверху заказы этого рейса (отмечены), ниже кандидаты: «Получено в США» и
 * «Рейс», поставленный кликом из списка без выбора рейса. Галка сразу
 * привязывает (и переводит «Получено в США» → «Рейс»), снятие — отвязывает.
 */
export default function FlightPage() {
  const { id } = useParams<{ id: string }>();
  const flightId = Number(id);
  const router = useRouter();
  const qc = useQueryClient();
  const [q, setQ] = useState("");
  const [busyIds, setBusyIds] = useState<Set<number>>(new Set());
  const [editing, setEditing] = useState(false);

  const { data: detail, isLoading } = useQuery({
    queryKey: ["flight", flightId],
    queryFn: () => api.get<FlightDetail>(`/api/flights/${flightId}`),
  });
  const { data: atWarehouse } = useQuery({
    queryKey: ["orders", { status: "at_warehouse" }],
    queryFn: () => api.get<OrderListItem[]>("/api/orders", { status: "at_warehouse" }),
  });
  const { data: inFlight } = useQuery({
    queryKey: ["orders", { status: "in_flight" }],
    queryFn: () => api.get<OrderListItem[]>("/api/orders", { status: "in_flight" }),
  });

  const needle = q.trim().toLowerCase();
  const onFlight = useMemo(
    () => [...(detail?.orders ?? [])].sort(byClient),
    [detail],
  );
  const candidates = useMemo(() => {
    const here = new Set(onFlight.map((o) => o.id));
    const unlinked = (inFlight ?? []).filter((o) => o.flight_id === null);
    return [...(atWarehouse ?? []), ...unlinked].filter((o) => !here.has(o.id)).sort(byClient);
  }, [onFlight, atWarehouse, inFlight]);

  const send = (add: number[], remove: number[]) =>
    api.post<FlightDetail>(`/api/flights/${flightId}/orders`, { add, remove });

  const refresh = (d: FlightDetail) => {
    qc.setQueryData(["flight", flightId], d);
    for (const key of ["flights", "orders", "order", "dashboard", "clients", "client", "money"])
      qc.invalidateQueries({ queryKey: [key] });
  };

  // Блокируем только затронутые строки — можно щёлкать галки подряд, не дожидаясь ответа.
  const apply = (add: number[], remove: number[], title: string) => {
    const ids = [...add, ...remove];
    setBusyIds((s) => new Set([...s, ...ids]));
    send(add, remove)
      .then((d) => {
        refresh(d);
        toastSaved(
          () =>
            send(remove, add)
              .then(refresh)
              .catch((e: ApiError) => toastError(e.message)),
          title,
        );
      })
      .catch((e: ApiError) => toastError(e.message))
      .finally(() =>
        setBusyIds((s) => {
          const n = new Set(s);
          ids.forEach((i) => n.delete(i));
          return n;
        }),
      );
  };

  const toggle = (o: OrderListItem, checked: boolean) =>
    checked ? apply([o.id], [], `#${o.id} в рейсе`) : apply([], [o.id], `#${o.id} снят с рейса`);

  const remove = () => {
    if (!detail) return;
    api
      .del(`/api/flights/${flightId}`)
      .then(() => {
        toastSaved(undefined, "Рейс удалён");
        for (const key of ["flights", "orders", "dashboard", "money"])
          qc.invalidateQueries({ queryKey: [key] });
        router.push("/flights");
      })
      .catch((e: ApiError) => toastError(e.message));
  };

  if (isLoading || !detail)
    return <p className="py-16 text-center text-[13px] text-muted">Загрузка…</p>;

  const weight = onFlight.reduce((s, o) => s + kg(o), 0);
  const unweighed = onFlight.filter((o) => !o.weight_kg).length;
  const shownOn = onFlight.filter((o) => matches(o, needle));
  const shownCand = candidates.filter((o) => matches(o, needle));
  const loadingCand = atWarehouse === undefined || inFlight === undefined;

  // рендер-функция, а не компонент: иначе строки перемонтируются на каждый рендер
  const row = (o: OrderListItem, checked: boolean) => {
    const busy = busyIds.has(o.id);
    return (
      <label
        key={o.id}
        className={cx(
          "flex cursor-pointer items-center gap-3 px-3 py-3 transition-colors hover:bg-surface2/60 sm:px-4 sm:py-2.5",
          busy && "pointer-events-none opacity-60",
        )}
      >
        <input
          type="checkbox"
          className="size-5 shrink-0 accent-[var(--color-accent)] sm:size-4"
          checked={checked}
          disabled={busy}
          onChange={(e) => toggle(o, e.target.checked)}
        />
        <span className="min-w-0 flex-1">
          <span className="block truncate text-[14px] font-medium sm:text-[13px]">
            {o.client_name}
            <span className="font-normal text-muted"> · {o.items}</span>
          </span>
          <span className="block truncate text-[12.5px] text-muted sm:text-[12px]">
            <Link
              href={`/orders/${o.id}`}
              className="hover:text-accent hover:underline"
              onClick={(e) => e.stopPropagation()}
            >
              #{o.id}
            </Link>{" "}
            · {o.store}
            <span className="sm:hidden"> · {o.weight_kg ? `${parseFloat(o.weight_kg)} кг` : "не взвешен"}</span>
          </span>
        </span>
        <span className="hidden w-20 shrink-0 text-right text-[12.5px] text-muted tnum sm:inline">
          {o.weight_kg ? `${parseFloat(o.weight_kg)} кг` : "— кг"}
        </span>
        <span className="hidden w-24 shrink-0 text-right text-[12.5px] tnum sm:inline">
          {fmtMoney(o.purchase_price_usd)}
        </span>
        <span className="shrink-0">
          {/* «Рейс» среди кандидатов = стоит статус, но рейс не выбран */}
          {!checked && o.status === "in_flight" ? (
            <span className="rounded-full bg-violet-500/12 px-2 py-0.5 text-[11.5px] font-medium whitespace-nowrap text-violet-700 dark:text-violet-400">
              Рейс · не привязан
            </span>
          ) : (
            <StatusBadge status={o.status} />
          )}
        </span>
      </label>
    );
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="text-[12.5px] text-muted">
            <Link href="/flights" className="hover:text-ink">
              Рейсы
            </Link>{" "}
            /
          </div>
          <h1 className="text-[17px] font-semibold tracking-tight tnum">
            Рейс {fmtDateFull(detail.departed_on)}
          </h1>
          {detail.description && (
            <p className="truncate text-[13px] text-muted">{detail.description}</p>
          )}
        </div>
        <div className="flex gap-1.5">
          <Button onClick={() => setEditing(true)}>Изменить</Button>
          <Button variant="danger" onClick={remove}>
            Удалить
          </Button>
        </div>
      </div>

      <Card className="grid grid-cols-3 divide-x divide-line">
        <div className="px-3 py-3 sm:px-4">
          <div className="text-[12px] font-medium text-muted">Заказов</div>
          <div className="mt-0.5 text-[20px] leading-tight font-semibold tnum">{onFlight.length}</div>
        </div>
        <div className="px-3 py-3 sm:px-4">
          <div className="text-[12px] font-medium text-muted">Вес</div>
          <div className="mt-0.5 text-[20px] leading-tight font-semibold tnum">
            {+weight.toFixed(3)} <span className="text-[13px] font-normal text-muted">кг</span>
          </div>
          {unweighed > 0 && (
            <div className="text-[11.5px] text-amber-700 dark:text-amber-400">
              не взвешено: {unweighed}
            </div>
          )}
        </div>
        <div className="px-3 py-3 sm:px-4">
          <div className="text-[12px] font-medium text-muted">Стоимость</div>
          <div className="mt-0.5 text-[20px] leading-tight font-semibold tnum">
            {fmtMoney(detail.cost_usd)}
          </div>
        </div>
      </Card>

      <Input
        type="search"
        placeholder="Найти: клиент, товар, магазин, номер…"
        value={q}
        onChange={(e) => setQ(e.target.value)}
      />

      <Card>
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-line px-3 py-2 sm:px-4">
          <div className="flex items-baseline gap-2">
            <h2 className="text-[13px] font-semibold">Ждут рейса</h2>
            <span className="text-[12.5px] text-muted tnum">{candidates.length}</span>
          </div>
          {shownCand.length > 1 && (
            <Button
              variant="ghost"
              className="h-7"
              disabled={shownCand.some((o) => busyIds.has(o.id))}
              onClick={() =>
                apply(
                  shownCand.map((o) => o.id),
                  [],
                  `В рейс добавлено: ${shownCand.length}`,
                )
              }
            >
              Отметить {needle ? "найденные" : "все"} ({shownCand.length})
            </Button>
          )}
        </div>
        {loadingCand ? (
          <p className="px-4 py-5 text-[13px] text-muted">Загрузка…</p>
        ) : candidates.length === 0 ? (
          <p className="px-4 py-5 text-[13px] text-muted">
            Ждущих нет: всё, что «Получено в США», уже распределено по рейсам.
          </p>
        ) : shownCand.length === 0 ? (
          <p className="px-4 py-5 text-[13px] text-muted">По запросу ничего.</p>
        ) : (
          <div className="divide-y divide-line/60">{shownCand.map((o) => row(o, false))}</div>
        )}
        <p className="border-t border-line px-4 py-2.5 text-[12px] text-muted">
          Отмеченный заказ «Получено в США» переходит в «Рейс», снятый — возвращается обратно.
        </p>
      </Card>

      <Card>
        <div className="flex items-baseline gap-2 border-b border-line px-3 py-2.5 sm:px-4">
          <h2 className="text-[13px] font-semibold">В этом рейсе</h2>
          <span className="text-[12.5px] text-muted tnum">{onFlight.length}</span>
        </div>
        {onFlight.length === 0 ? (
          <p className="px-4 py-5 text-[13px] text-muted">Пока пусто — отметьте заказы ниже.</p>
        ) : shownOn.length === 0 ? (
          <p className="px-4 py-5 text-[13px] text-muted">По запросу ничего.</p>
        ) : (
          <div className="divide-y divide-line/60">{shownOn.map((o) => row(o, true))}</div>
        )}
      </Card>

      <EditFlightModal flight={editing ? detail : null} onClose={() => setEditing(false)} />
    </div>
  );
}
