"use client";

import { FormEvent, useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { Flight, FlightDetail } from "@/lib/api-types";
import { fmtDateFull, fmtMoney, isoToday } from "@/lib/format";
import { Button, Card, EmptyState, Field, Input, Modal, Section } from "@/components/ui";
import { DatePicker } from "@/components/date-picker";
import { OrdersTable } from "@/components/orders-table";
import { toastError, toastSaved } from "@/components/toasts";
import { cx } from "@/components/ui";

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
            <DatePicker className="w-full" value={date} onChange={(v) => setDate(v ?? isoToday())} />
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
      .then(() => {
        setCost("");
        setDesc("");
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
          <Button type="submit" variant="primary" className="w-full sm:w-auto" disabled={!cost.trim()}>
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
                  <td className="px-3 py-2.5 text-right text-[13px] tnum">{f.orders_count ?? "—"}</td>
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

      {selected !== null && detail && (
        <Section title={`Заказы рейса от ${fmtDateFull(detail.departed_on)}`}>
          {detail.orders.length === 0 ? (
            <p className="text-[12.5px] text-muted">
              К рейсу пока не привязан ни один заказ (поле «Рейс» в карточке заказа).
            </p>
          ) : (
            <OrdersTable orders={detail.orders} showClient />
          )}
        </Section>
      )}

      <EditFlightModal flight={editing} onClose={() => setEditing(null)} />
    </div>
  );
}
