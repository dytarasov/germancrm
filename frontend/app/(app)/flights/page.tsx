"use client";

import { FormEvent, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { Flight } from "@/lib/api-types";
import { fmtDateFull, fmtMoney, isoToday, plural } from "@/lib/format";
import { Button, Card, EmptyState, Input, Modal } from "@/components/ui";
import { DatePicker } from "@/components/date-picker";
import { toastError, toastSaved } from "@/components/toasts";

export default function FlightsPage() {
  const qc = useQueryClient();
  const router = useRouter();
  const [date, setDate] = useState(isoToday());
  const [cost, setCost] = useState("");
  const [desc, setDesc] = useState("");
  const [adding, setAdding] = useState(false);

  const { data: flights, isLoading } = useQuery({
    queryKey: ["flights"],
    queryFn: () => api.get<Flight[]>("/api/flights"),
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
        toastSaved(undefined, "Рейс добавлен");
        qc.invalidateQueries({ queryKey: ["flights"] });
        qc.invalidateQueries({ queryKey: ["dashboard"] });
        qc.invalidateQueries({ queryKey: ["money"] });
        setAdding(false);
        router.push(`/flights/${f.id}`); // сразу к распределению заказов
      })
      .catch((err) => toastError(err.message));
  };

  const newFlightForm = (
    <form onSubmit={add} className="flex flex-wrap items-end gap-2">
      <div>
        <div className="mb-1 text-[12px] font-medium text-muted">Дата вылета</div>
        <DatePicker value={date} onChange={(v) => setDate(v ?? isoToday())} />
      </div>
      <div>
        <div className="mb-1 text-[12px] font-medium text-muted">Стоимость, $</div>
        <Input
          className="w-32 tnum"
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
  );

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-2">
        <h1 className="text-[17px] font-semibold tracking-tight">Рейсы</h1>
        {/* на телефоне форма не занимает весь экран — открывается по кнопке */}
        <Button variant="primary" className="sm:hidden" onClick={() => setAdding(true)}>
          Новый рейс
        </Button>
      </div>

      <Card className="hidden p-3 sm:block">{newFlightForm}</Card>

      <Modal open={adding} onClose={() => setAdding(false)} title="Новый рейс">
        {newFlightForm}
      </Modal>

      <Card>
        {isLoading ? (
          <p className="py-12 text-center text-[13px] text-muted">Загрузка…</p>
        ) : (flights ?? []).length === 0 ? (
          <EmptyState
            title="Рейсов пока нет"
            hint="Добавляйте каждую отправку партии США → Москва: дата и стоимость идут в расчёт прибыли."
          />
        ) : (
          // Строка рейса — ссылка на его страницу: там галки, правка и удаление.
          <ul className="divide-y divide-line/60">
            {(flights ?? []).map((f) => (
              <li key={f.id}>
                <Link
                  href={`/flights/${f.id}`}
                  className="flex items-center gap-3 px-3 py-3 transition-colors hover:bg-surface2/60 active:bg-surface2/60 sm:px-4"
                >
                  <span className="min-w-0 flex-1">
                    <span className="block text-[13.5px] font-medium tnum">
                      {fmtDateFull(f.departed_on)}
                    </span>
                    <span className="block truncate text-[12.5px] text-muted">
                      {f.description ?? "без описания"}
                    </span>
                  </span>
                  <span className="shrink-0 text-right">
                    <span className="block text-[13px] tnum">
                      {f.orders_count ?? 0} {plural(f.orders_count ?? 0, "заказ", "заказа", "заказов")}
                    </span>
                    <span className="block text-[12.5px] text-muted tnum">{fmtMoney(f.cost_usd)}</span>
                  </span>
                  <svg
                    className="size-4 shrink-0 text-muted/60"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                    strokeLinecap="round"
                    aria-hidden
                  >
                    <path d="M9 6l6 6-6 6" />
                  </svg>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </Card>

    </div>
  );
}
