"use client";

import { FormEvent, useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { Flight, FlightDetail, OrderListItem } from "@/lib/api-types";
import { fmtDateFull, fmtMoney, isoToday } from "@/lib/format";
import { Button, Card, EmptyState, Field, Input, Modal } from "@/components/ui";
import { DatePicker } from "@/components/date-picker";
import { StatusBadge } from "@/components/status-badge";
import { toastError, toastSaved } from "@/components/toasts";
import { cx } from "@/components/ui";

const kg = (o: OrderListItem) => (o.weight_kg ? parseFloat(o.weight_kg) : 0);

/**
 * Распределение по рейсу галками: сверху заказы этого рейса (отмечены),
 * ниже все «Получено в США» — клик по галке сразу привязывает и переводит в «Рейс».
 */
function FlightOrders({ detail }: { detail: FlightDetail }) {
  const qc = useQueryClient();
  const [busy, setBusy] = useState(false);
  const { data: waiting } = useQuery({
    queryKey: ["orders", { status: "at_warehouse" }],
    queryFn: () => api.get<OrderListItem[]>("/api/orders", { status: "at_warehouse" }),
  });

  const onFlight = new Set(detail.orders.map((o) => o.id));
  const candidates = (waiting ?? []).filter((o) => !onFlight.has(o.id));
  const weight = detail.orders.reduce((s, o) => s + kg(o), 0);
  const unweighed = detail.orders.filter((o) => !o.weight_kg).length;

  const send = (add: number[], remove: number[]) =>
    api.post<FlightDetail>(`/api/flights/${detail.id}/orders`, { add, remove });

  const refresh = (d: FlightDetail) => {
    qc.setQueryData(["flight", detail.id], d);
    for (const key of ["flights", "orders", "order", "dashboard", "clients", "client", "money"])
      qc.invalidateQueries({ queryKey: [key] });
  };

  const apply = (add: number[], remove: number[], title: string) => {
    setBusy(true);
    send(add, remove)
      .then((d) => {
        refresh(d);
        // откат: обратная операция тем же эндпоинтом
        toastSaved(
          () =>
            send(remove, add)
              .then(refresh)
              .catch((e) => toastError(e.message)),
          title,
        );
      })
      .catch((e) => toastError(e.message))
      .finally(() => setBusy(false));
  };

  const toggle = (o: OrderListItem, checked: boolean) =>
    checked ? apply([o.id], [], `#${o.id} в рейсе`) : apply([], [o.id], `#${o.id} снят с рейса`);

  // рендер-функция, а не компонент: иначе строки перемонтируются на каждый рендер
  const row = (o: OrderListItem, checked: boolean) => (
    <label
      key={o.id}
      className={cx(
        "flex cursor-pointer items-center gap-3 px-3 py-2 hover:bg-surface2/60",
        busy && "pointer-events-none opacity-70",
      )}
    >
      <input
        type="checkbox"
        className="size-4 shrink-0 accent-[var(--color-accent)]"
        checked={checked}
        disabled={busy}
        onChange={(e) => toggle(o, e.target.checked)}
      />
      <span className="min-w-0 flex-1">
        <span className="block truncate text-[13px] font-medium">
          {o.client_name}
          <span className="font-normal text-muted"> · {o.items}</span>
        </span>
        <span className="block truncate text-[12px] text-muted">
          #{o.id} · {o.store}
          {o.store_order_number && <span className="ml-1.5 font-mono">{o.store_order_number}</span>}
        </span>
      </span>
      <span className="hidden shrink-0 font-mono text-[12.5px] text-muted tnum sm:inline">
        {o.weight_kg ? `${parseFloat(o.weight_kg)} кг` : "— кг"}
      </span>
      <span className="hidden w-24 shrink-0 text-right font-mono text-[12.5px] tnum sm:inline">
        {fmtMoney(o.purchase_price_usd)}
      </span>
      <span className="shrink-0">
        <StatusBadge status={o.status} />
      </span>
    </label>
  );

  return (
    <div className="space-y-3">
      <Card>
        <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1 border-b border-line px-3 py-2.5">
          <h2 className="text-[12.5px] font-semibold">
            В рейсе от {fmtDateFull(detail.departed_on)}
            <span className="ml-2 font-normal text-muted">{detail.orders.length}</span>
          </h2>
          {detail.orders.length > 0 && (
            <span className="text-[12px] text-muted">
              {weight > 0 && <span className="font-mono tnum">{+weight.toFixed(3)} кг</span>}
              {unweighed > 0 && ` · не взвешено: ${unweighed}`}
            </span>
          )}
        </div>
        {detail.orders.length === 0 ? (
          <p className="px-3 py-4 text-[12.5px] text-muted">Пока пусто — отметьте заказы ниже.</p>
        ) : (
          <div className="divide-y divide-line/60">{detail.orders.map((o) => row(o, true))}</div>
        )}
      </Card>

      <Card>
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-line px-3 py-2">
          <h2 className="text-[12.5px] font-semibold">
            Получено в США — ждут рейса
            <span className="ml-2 font-normal text-muted">{candidates.length}</span>
          </h2>
          {candidates.length > 1 && (
            <Button
              variant="ghost"
              className="h-7"
              disabled={busy}
              onClick={() =>
                apply(
                  candidates.map((o) => o.id),
                  [],
                  `В рейс добавлено: ${candidates.length}`,
                )
              }
            >
              Отметить все
            </Button>
          )}
        </div>
        {waiting === undefined ? (
          <p className="px-3 py-4 text-[12.5px] text-muted">Загрузка…</p>
        ) : candidates.length === 0 ? (
          <p className="px-3 py-4 text-[12.5px] text-muted">
            Заказов в статусе «Получено в США» нет.
          </p>
        ) : (
          <div className="divide-y divide-line/60">{candidates.map((o) => row(o, false))}</div>
        )}
      </Card>
    </div>
  );
}

function EditFlightModal({ flight, onClose }: { flight: Flight | null; onClose: () => void }) {
  const qc = useQueryClient();
  const [date, setDate] = useState(isoToday());
  const [cost, setCost] = useState("");
  const [desc, setDesc] = useState("");
  const [busy, setBusy] = useState(false);

  // При каждом открытии заполняем форму текущими значениями рейса.
  useEffect(() => {
    if (flight) {
      setDate(flight.departed_on);
      setCost(flight.cost_usd);
      setDesc(flight.description ?? "");
    }
  }, [flight]);

  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (!flight) return;
    setBusy(true);
    api
      .patch<Flight>(`/api/flights/${flight.id}`, {
        departed_on: date,
        cost_usd: cost.trim(),
        description: desc.trim() || null,
      })
      .then(() => {
        toastSaved(undefined, "Рейс обновлён");
        qc.invalidateQueries({ queryKey: ["flights"] });
        qc.invalidateQueries({ queryKey: ["flight", flight.id] });
        qc.invalidateQueries({ queryKey: ["dashboard"] });
        qc.invalidateQueries({ queryKey: ["money"] });
        onClose();
      })
      .catch((err) => toastError(err.message))
      .finally(() => setBusy(false));
  };

  return (
    <Modal open={flight !== null} onClose={onClose} title="Изменить рейс">
      <form onSubmit={submit} className="space-y-3">
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <Field label="Дата вылета">
            <DatePicker
              className="w-full"
              value={date}
              onChange={(v) => setDate(v ?? isoToday())}
            />
          </Field>
          <Field label="Стоимость, $">
            <Input
              className="font-mono"
              placeholder="0.00"
              inputMode="decimal"
              value={cost}
              onChange={(e) => setCost(e.target.value)}
            />
          </Field>
        </div>
        <Field label="Описание">
          <Input
            placeholder="партия №, вес, примечание…"
            value={desc}
            onChange={(e) => setDesc(e.target.value)}
          />
        </Field>
        <div className="flex justify-end gap-2 pt-1">
          <Button type="button" variant="ghost" onClick={onClose}>
            Отмена
          </Button>
          <Button type="submit" variant="primary" disabled={!cost.trim() || busy}>
            {busy ? "Сохраняю…" : "Сохранить"}
          </Button>
        </div>
      </form>
    </Modal>
  );
}

export default function FlightsPage() {
  const qc = useQueryClient();
  const [date, setDate] = useState(isoToday());
  const [cost, setCost] = useState("");
  const [desc, setDesc] = useState("");
  const [selected, setSelected] = useState<number | null>(null);
  const [editing, setEditing] = useState<Flight | null>(null);

  const { data: flights, isLoading } = useQuery({
    queryKey: ["flights"],
    queryFn: () => api.get<Flight[]>("/api/flights"),
  });

  const { data: detail } = useQuery({
    queryKey: ["flight", selected],
    queryFn: () => api.get<FlightDetail>(`/api/flights/${selected}`),
    enabled: selected !== null,
  });

  const add = (e: FormEvent) => {
    e.preventDefault();
    api
      .post<Flight>("/api/flights", {
        departed_on: date,
        cost_usd: cost.trim(),
        description: desc.trim() || undefined,
      })
      .then((f) => {
        setCost("");
        setDesc("");
        setSelected(f.id); // сразу открываем распределение заказов
        toastSaved(undefined, "Рейс добавлен");
        qc.invalidateQueries({ queryKey: ["flights"] });
        qc.invalidateQueries({ queryKey: ["dashboard"] });
        qc.invalidateQueries({ queryKey: ["money"] });
      })
      .catch((err) => toastError(err.message));
  };

  const remove = (f: Flight) => {
    api
      .del(`/api/flights/${f.id}`)
      .then(() => {
        toastSaved(undefined, "Рейс удалён");
        if (selected === f.id) setSelected(null);
        qc.invalidateQueries({ queryKey: ["flights"] });
        qc.invalidateQueries({ queryKey: ["dashboard"] });
        qc.invalidateQueries({ queryKey: ["money"] });
      })
      .catch((err) => toastError(err.message));
  };

  return (
    <div className="space-y-4">
      <h1 className="text-[17px] font-semibold tracking-tight">Рейсы</h1>

      <Card className="p-3">
        <form onSubmit={add} className="flex flex-wrap items-end gap-2">
          <div>
            <div className="mb-1 text-[12px] font-medium text-muted">Дата вылета</div>
            <DatePicker value={date} onChange={(v) => setDate(v ?? isoToday())} />
          </div>
          <div>
            <div className="mb-1 text-[12px] font-medium text-muted">Стоимость, $</div>
            <Input
              className="w-32 font-mono"
              placeholder="0.00"
              inputMode="decimal"
              value={cost}
              onChange={(e) => setCost(e.target.value)}
            />
          </div>
          <div className="min-w-44 flex-1">
            <div className="mb-1 text-[12px] font-medium text-muted">Описание</div>
            <Input
              placeholder="партия №, вес, примечание…"
              value={desc}
              onChange={(e) => setDesc(e.target.value)}
            />
          </div>
          <Button
            type="submit"
            variant="primary"
            className="w-full sm:w-auto"
            disabled={!cost.trim()}
          >
            Добавить рейс
          </Button>
        </form>
      </Card>

      <Card>
        {isLoading ? (
          <p className="py-12 text-center text-[13px] text-muted">Загрузка…</p>
        ) : (flights ?? []).length === 0 ? (
          <EmptyState
            title="Рейсов пока нет"
            hint="Добавляйте каждую отправку партии США → Москва: дата и стоимость идут в расчёт прибыли."
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[600px]">
              <thead>
                <tr className="border-b border-line text-left text-[11.5px] tracking-wide text-muted uppercase">
                  <th className="px-3 py-2 font-medium">Дата</th>
                  <th className="px-3 py-2 text-right font-medium">Стоимость</th>
                  <th className="px-3 py-2 font-medium">Описание</th>
                  <th className="px-3 py-2 text-right font-medium">Заказов</th>
                  <th className="px-3 py-2" />
                </tr>
              </thead>
              <tbody>
                {(flights ?? []).map((f) => (
                  <tr
                    key={f.id}
                    tabIndex={0}
                    role="button"
                    aria-expanded={selected === f.id}
                    onClick={() => setSelected(selected === f.id ? null : f.id)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault();
                        setSelected(selected === f.id ? null : f.id);
                      }
                    }}
                    className={cx(
                      "cursor-pointer border-b border-line/60 last:border-0 hover:bg-surface2/60",
                      selected === f.id && "bg-surface2/70",
                    )}
                  >
                    <td className="px-3 py-2.5 text-[13px]">{fmtDateFull(f.departed_on)}</td>
                    <td className="px-3 py-2.5 text-right font-mono text-[13px] tnum">
                      {fmtMoney(f.cost_usd)}
                    </td>
                    <td className="px-3 py-2.5 text-[13px] text-muted">{f.description ?? "—"}</td>
                    <td className="px-3 py-2.5 text-right text-[13px] tnum">
                      {f.orders_count ?? "—"}
                    </td>
                    <td className="px-3 py-2.5 text-right whitespace-nowrap">
                      <Button
                        variant="ghost"
                        className="h-7"
                        onClick={(e) => {
                          e.stopPropagation();
                          setEditing(f);
                        }}
                      >
                        Изменить
                      </Button>
                      <Button
                        variant="ghost"
                        className="h-7"
                        onClick={(e) => {
                          e.stopPropagation();
                          remove(f);
                        }}
                      >
                        Удалить
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {selected === null
        ? (flights ?? []).length > 0 && (
            <p className="text-[12.5px] text-muted">
              Выберите рейс в таблице — ниже появятся заказы «Получено в США», их можно отметить
              галками.
            </p>
          )
        : detail && detail.id === selected && <FlightOrders detail={detail} />}

      <EditFlightModal flight={editing} onClose={() => setEditing(null)} />
    </div>
  );
}
