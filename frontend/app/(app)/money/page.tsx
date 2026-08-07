"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { MoneyReport } from "@/lib/api-types";
import { fmtDate, fmtDateFull, fmtMoney, fmtMonth, toLocalISO } from "@/lib/format";
import { Card, Section, Seg } from "@/components/ui";
import { DateRangePicker } from "@/components/date-picker";

type Preset = "month" | "prev" | "year" | "custom";

const iso = toLocalISO;

export default function MoneyPage() {
  const [preset, setPreset] = useState<Preset>("month");
  const [customFrom, setCustomFrom] = useState("");
  const [customTo, setCustomTo] = useState("");

  const { from, to } = useMemo(() => {
    const now = new Date();
    if (preset === "month") return { from: iso(new Date(now.getFullYear(), now.getMonth(), 1)), to: iso(now) };
    if (preset === "prev")
      return {
        from: iso(new Date(now.getFullYear(), now.getMonth() - 1, 1)),
        to: iso(new Date(now.getFullYear(), now.getMonth(), 0)),
      };
    if (preset === "year") return { from: iso(new Date(now.getFullYear(), 0, 1)), to: iso(now) };
    return { from: customFrom, to: customTo };
  }, [preset, customFrom, customTo]);

  const enabled = Boolean(from && to);
  const { data, isLoading } = useQuery({
    queryKey: ["money", from, to],
    queryFn: () => api.get<MoneyReport>("/api/reports/money", { from, to }),
    enabled,
  });

  return (
    <div className="space-y-4">
      <h1 className="text-[17px] font-semibold tracking-tight">Деньги</h1>

      <div className="flex flex-wrap items-center gap-2">
        <Seg
          value={preset}
          onChange={setPreset}
          options={[
            { value: "month", label: "Этот месяц" },
            { value: "prev", label: "Прошлый" },
            { value: "year", label: "Год" },
            { value: "custom", label: "Период" },
          ]}
        />
        {preset === "custom" && (
          <DateRangePicker
            from={customFrom || null}
            to={customTo || null}
            onChange={(f, t) => {
              setCustomFrom(f ?? "");
              setCustomTo(t ?? "");
            }}
          />
        )}
      </div>

      {!enabled ? (
        <p className="py-10 text-center text-[13px] text-muted">Выберите период</p>
      ) : isLoading || !data ? (
        <p className="py-10 text-center text-[13px] text-muted">Загрузка…</p>
      ) : (
        <>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            <Card className="p-4">
              <div className="text-[12px] text-muted">Комиссии (закрытые заказы)</div>
              <div className="mt-1 font-mono text-[24px] font-semibold tnum">
                {fmtMoney(data.commissions_usd)}
              </div>
            </Card>
            <Card className="p-4">
              <div className="text-[12px] text-muted">Расходы на рейсы</div>
              <div className="mt-1 font-mono text-[24px] font-semibold tnum">
                −{fmtMoney(data.flights_cost_usd)}
              </div>
            </Card>
            <Card className="p-4">
              <div className="text-[12px] text-muted">Прибыль</div>
              <div
                className={
                  "mt-1 font-mono text-[24px] font-semibold tnum " +
                  (parseFloat(data.profit_usd) >= 0
                    ? "text-green-600 dark:text-green-400"
                    : "text-red-600 dark:text-red-400")
                }
              >
                {fmtMoney(data.profit_usd)}
              </div>
            </Card>
          </div>

          {data.months.length > 1 && (
            <Section title="По месяцам">
              <div className="overflow-x-auto">
              <table className="w-full min-w-[480px]">
                <thead>
                  <tr className="border-b border-line text-left text-[11.5px] tracking-wide text-muted uppercase">
                    <th className="px-3 py-2 font-medium">Месяц</th>
                    <th className="px-3 py-2 text-right font-medium">Комиссии</th>
                    <th className="px-3 py-2 text-right font-medium">Рейсы</th>
                    <th className="px-3 py-2 text-right font-medium">Прибыль</th>
                  </tr>
                </thead>
                <tbody>
                  {data.months.map((m) => (
                    <tr key={m.month} className="border-b border-line/60 last:border-0">
                      <td className="px-3 py-2 text-[13px]">{fmtMonth(m.month)}</td>
                      <td className="px-3 py-2 text-right font-mono text-[12.5px] tnum">
                        {fmtMoney(m.commissions_usd)}
                      </td>
                      <td className="px-3 py-2 text-right font-mono text-[12.5px] tnum">
                        −{fmtMoney(m.flights_cost_usd)}
                      </td>
                      <td className="px-3 py-2 text-right font-mono text-[12.5px] font-semibold tnum">
                        {fmtMoney(m.profit_usd)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              </div>
            </Section>
          )}

          <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
            <Section title={`Заказы в расчёте (${data.orders.length})`}>
              {data.orders.length === 0 ? (
                <p className="text-[12.5px] text-muted">За период не закрыто ни одного заказа</p>
              ) : (
                <ul className="divide-y divide-line/60">
                  {data.orders.map((o) => (
                    <li key={o.id}>
                      <Link
                        href={`/orders/${o.id}`}
                        className="flex items-baseline justify-between gap-3 py-2 hover:bg-surface2/50"
                      >
                        <span className="min-w-0">
                          <span className="block truncate text-[13px]">{o.items}</span>
                          <span className="block text-[12px] text-muted">
                            {o.client_name} · {o.store} · {fmtDate(o.closed_at)}
                          </span>
                        </span>
                        <span className="shrink-0 font-mono text-[12.5px] font-medium tnum">
                          {fmtMoney(o.commission_usd)}
                        </span>
                      </Link>
                    </li>
                  ))}
                </ul>
              )}
            </Section>
            <Section title={`Рейсы за период (${data.flights.length})`}>
              {data.flights.length === 0 ? (
                <p className="text-[12.5px] text-muted">Рейсов за период не было</p>
              ) : (
                <ul className="divide-y divide-line/60">
                  {data.flights.map((f) => (
                    <li key={f.id} className="flex items-baseline justify-between gap-3 py-2">
                      <span className="min-w-0">
                        <span className="block text-[13px]">{fmtDateFull(f.departed_on)}</span>
                        {f.description && (
                          <span className="block truncate text-[12px] text-muted">{f.description}</span>
                        )}
                      </span>
                      <span className="shrink-0 font-mono text-[12.5px] tnum">
                        −{fmtMoney(f.cost_usd)}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </Section>
          </div>
        </>
      )}
    </div>
  );
}
