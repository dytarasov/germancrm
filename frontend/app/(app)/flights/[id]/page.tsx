"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
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

/** Кто может ехать рейсом. Порядок — от готовых к отправке к только что купленным:
 * письма о складе бывает нет (магазин не прислал, LLM не разобрал), поэтому
 * галка переводит в «Рейс» из любого из этих статусов. */
const CANDIDATE_GROUPS: {
  key: string;
  title: string;
  match: (o: OrderListItem) => boolean;
  bulk?: boolean; // «Отметить все» — только где это безопасно
}[] = [
  { key: "wh", title: "Получено в США", match: (o) => o.status === "at_warehouse", bulk: true },
  {
    key: "unlinked",
    title: "«Рейс» без привязки к рейсу",
    match: (o) => o.status === "in_flight" && o.flight_id === null,
    bulk: true,
  },
  { key: "shipped", title: "Отправлен — ещё едет на склад", match: (o) => o.status === "shipped" },
  { key: "purchased", title: "Куплен", match: (o) => o.status === "purchased" },
];

function matches(o: OrderListItem, q: string): boolean {
  if (!q) return true;
  const hay = `${o.client_name} ${o.items} ${o.store} ${o.store_order_number ?? ""} #${o.id}`;
  return hay.toLowerCase().includes(q);
}

/**
 * Страница рейса: что в нём едет — галками.
 * Галки — только черновик: отметил всё, что едет (и снял лишнее), нажал
 * «Подтвердить» — уходит одним пакетом, статусы меняются разом.
 */
export default function FlightPage() {
  const { id } = useParams<{ id: string }>();
  const flightId = Number(id);
  const router = useRouter();
  const qc = useQueryClient();
  const [q, setQ] = useState("");
  // Черновик галок: id → отмечен ли. Пусто = всё как на сервере.
  // На сервер уходит только по «Подтвердить» — одним пакетом.
  const [draft, setDraft] = useState<Map<number, boolean>>(new Map());
  const [saving, setSaving] = useState(false);
  const [editing, setEditing] = useState(false);

  const { data: detail, isLoading } = useQuery({
    queryKey: ["flight", flightId],
    queryFn: () => api.get<FlightDetail>(`/api/flights/${flightId}`),
  });
  // тот же запрос, что у дашборда, — кэш общий
  const { data: active } = useQuery({
    queryKey: ["orders", { active: true }],
    queryFn: () => api.get<OrderListItem[]>("/api/orders?active=true"),
  });

  const needle = q.trim().toLowerCase();
  const onFlight = useMemo(
    () => [...(detail?.orders ?? [])].sort(byClient),
    [detail],
  );
  const candidates = useMemo(() => {
    const here = new Set(onFlight.map((o) => o.id));
    return (active ?? [])
      .filter((o) => !here.has(o.id) && CANDIDATE_GROUPS.some((g) => g.match(o)))
      .sort(byClient);
  }, [onFlight, active]);

  const send = (add: number[], remove: number[]) =>
    api.post<FlightDetail>(`/api/flights/${flightId}/orders`, { add, remove });

  const refresh = (d: FlightDetail) => {
    qc.setQueryData(["flight", flightId], d);
    for (const key of ["flights", "orders", "order", "dashboard", "clients", "client", "money"])
      qc.invalidateQueries({ queryKey: [key] });
  };

  const isChecked = (o: OrderListItem, onFlightNow: boolean) => draft.get(o.id) ?? onFlightNow;

  // Значение, совпадающее с сервером, из черновика убираем — чтобы счётчик был честным.
  const mark = (list: OrderListItem[], value: boolean, onFlightNow: boolean) =>
    setDraft((d) => {
      const n = new Map(d);
      for (const o of list) {
        if (value === onFlightNow) n.delete(o.id);
        else n.set(o.id, value);
      }
      return n;
    });

  const toAdd = candidates.filter((o) => draft.get(o.id) === true);
  const toRemove = onFlight.filter((o) => draft.get(o.id) === false);
  const pending = toAdd.length + toRemove.length;

  // Неподтверждённые галки не теряем молча при закрытии вкладки.
  useEffect(() => {
    if (pending === 0) return;
    const h = (e: BeforeUnloadEvent) => e.preventDefault();
    window.addEventListener("beforeunload", h);
    return () => window.removeEventListener("beforeunload", h);
  }, [pending]);

  const confirm = () => {
    const add = toAdd.map((o) => o.id);
    const rem = toRemove.map((o) => o.id);
    setSaving(true);
    send(add, rem)
      .then((d) => {
        refresh(d);
        setDraft(new Map());
        const parts = [add.length && `в рейс: ${add.length}`, rem.length && `снято: ${rem.length}`];
        toastSaved(
          () =>
            send(rem, add)
              .then(refresh)
              .catch((e: ApiError) => toastError(e.message)),
          `Рейс обновлён — ${parts.filter(Boolean).join(", ")}`,
        );
      })
      .catch((e: ApiError) => toastError(e.message))
      .finally(() => setSaving(false));
  };

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
  const loadingCand = active === undefined;

  // рендер-функция, а не компонент: иначе строки перемонтируются на каждый рендер
  const row = (o: OrderListItem, onFlightNow: boolean) => {
    const checked = isChecked(o, onFlightNow);
    const changed = checked !== onFlightNow;
    return (
      <label
        key={o.id}
        className={cx(
          "flex cursor-pointer items-center gap-3 px-3 py-3 transition-colors sm:px-4 sm:py-2.5",
          changed ? "bg-accent-soft" : "hover:bg-surface2/60",
          saving && "pointer-events-none opacity-60",
        )}
      >
        <input
          type="checkbox"
          className="size-5 shrink-0 accent-[var(--color-accent)] sm:size-4"
          checked={checked}
          disabled={saving}
          onChange={(e) => mark([o], e.target.checked, onFlightNow)}
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
        <span className="shrink-0 sm:w-36 sm:text-right">
          {/* что произойдёт после «Подтвердить» */}
          {changed ? (
            <span className="text-[11.5px] font-medium whitespace-nowrap text-accent">
              {checked ? "→ в рейс" : "→ снять"}
            </span>
          ) : !onFlightNow && o.status === "in_flight" ? (
            /* «Рейс» среди кандидатов = стоит статус, но рейс не выбран */
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
        </div>
        {loadingCand ? (
          <p className="px-4 py-5 text-[13px] text-muted">Загрузка…</p>
        ) : candidates.length === 0 ? (
          <p className="px-4 py-5 text-[13px] text-muted">
            Ждущих нет: все активные заказы уже распределены по рейсам.
          </p>
        ) : shownCand.length === 0 ? (
          <p className="px-4 py-5 text-[13px] text-muted">По запросу ничего.</p>
        ) : (
          CANDIDATE_GROUPS.map((g) => {
            const list = shownCand.filter(g.match);
            if (list.length === 0) return null;
            return (
              <div key={g.key}>
                <div className="flex min-h-9 items-center justify-between gap-2 border-b border-line/60 bg-surface2/50 px-3 py-1 sm:px-4">
                  <span className="text-[11.5px] font-semibold tracking-wide text-muted uppercase">
                    {g.title} <span className="font-normal tnum">{list.length}</span>
                  </span>
                  {g.bulk && list.length > 1 && (
                    <Button
                      variant="ghost"
                      className="h-7"
                      disabled={saving}
                      onClick={() => mark(list, !list.every((o) => isChecked(o, false)), false)}
                    >
                      {list.every((o) => isChecked(o, false)) ? "Снять все" : "Отметить все"}
                    </Button>
                  )}
                </div>
                <div className="divide-y divide-line/60">{list.map((o) => row(o, false))}</div>
              </div>
            );
          })
        )}
        <p className="border-t border-line px-4 py-2.5 text-[12px] text-muted">
          Отметьте, что едет, и нажмите «Подтвердить»: отмеченные перейдут в «Рейс» из любого
          статуса, даже если письма о складе не было. Снятые с рейса вернутся в статус, который был до него.
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

      {pending > 0 && (
        // липнет к низу экрана, пока есть неподтверждённые галки
        <div className="sticky bottom-[calc(env(safe-area-inset-bottom)+0.75rem)] z-20 transition duration-200 ease-out starting:translate-y-3 starting:opacity-0">
          <div className="flex flex-wrap items-center gap-x-4 gap-y-2 rounded-xl border border-line bg-surface px-4 py-3 shadow-lg shadow-black/10">
            <span className="text-[13px] font-medium tnum">
              {toAdd.length > 0 && <>В рейс: {toAdd.length}</>}
              {toAdd.length > 0 && toRemove.length > 0 && " · "}
              {toRemove.length > 0 && <>Снять: {toRemove.length}</>}
            </span>
            <span className="ml-auto flex gap-2">
              <Button variant="ghost" disabled={saving} onClick={() => setDraft(new Map())}>
                Сбросить
              </Button>
              <Button variant="primary" disabled={saving} onClick={confirm}>
                {saving ? "Сохраняю…" : "Подтвердить"}
              </Button>
            </span>
          </div>
        </div>
      )}

      <EditFlightModal flight={editing ? detail : null} onClose={() => setEditing(false)} />
    </div>
  );
}
