"use client";

import { FormEvent, useEffect, useState } from "react";
import Link from "next/link";
import { keepPreviousData, useQuery, useQueryClient } from "@tanstack/react-query";
import { useDebounced } from "@/lib/use-debounced";
import { api } from "@/lib/api";
import type { OrderListItem, Track, TrackSuggestion } from "@/lib/api-types";
import { fmtDateTime } from "@/lib/format";
import { Badge, Button, Card, EmptyState, Input, Section } from "@/components/ui";
import { Combobox } from "@/components/combobox";
import { toastError, toastSaved } from "@/components/toasts";

function OpenTrackCard({ track, orders }: { track: Track; orders: OrderListItem[] }) {
  const qc = useQueryClient();
  const [manual, setManual] = useState("");

  const { data: suggestions } = useQuery({
    queryKey: ["track-suggestions", track.id],
    queryFn: () => api.get<TrackSuggestion[]>(`/api/tracks/${track.id}/suggestions`),
    staleTime: 30_000,
  });

  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["tracks"] });
    qc.invalidateQueries({ queryKey: ["dashboard"] });
    qc.invalidateQueries({ queryKey: ["orders"] });
    qc.invalidateQueries({ queryKey: ["order"] });
  };

  const assign = (orderId: number | null, label?: string) => {
    api
      .post(`/api/tracks/${track.id}/assign`, { order_id: orderId })
      .then(() => {
        toastSaved(
          () => api.post(`/api/tracks/${track.id}/assign`, { order_id: null }).then(refresh),
          label ? `Привязан к ${label}` : "Готово",
        );
        refresh();
      })
      .catch((e) => toastError(e.message));
  };

  const dismiss = () => {
    api
      .post(`/api/tracks/${track.id}/dismiss`)
      .then(() => {
        toastSaved(undefined, "Трек скрыт");
        refresh();
      })
      .catch((e) => toastError(e.message));
  };

  type Cand = {
    order_id: number;
    score: number;
    reasons: string[];
    order_label?: string;
    client_name?: string;
  };
  const list: Cand[] = (suggestions ?? track.candidates ?? []) as Cand[];

  return (
    <div className="rounded-lg border border-line p-3">
      <div className="flex items-center gap-2.5">
        <span className="font-mono text-[13.5px] font-medium">{track.tracking_number}</span>
        {track.carrier && <Badge className="bg-zinc-500/10 text-muted uppercase">{track.carrier}</Badge>}
        <Badge className="bg-zinc-500/10 text-muted">
          {track.source === "email" ? "из письма" : "вручную"}
        </Badge>
        <span className="ml-auto text-[11.5px] text-muted">{fmtDateTime(track.created_at)}</span>
      </div>

      {list.length > 0 && (
        <div className="mt-2.5 space-y-1.5">
          {list.slice(0, 3).map((s) => (
            <div key={s.order_id} className="flex flex-wrap items-center gap-2 text-[12.5px]">
              <Link href={`/orders/${s.order_id}`} className="font-medium hover:text-accent">
                {s.order_label ?? `Заказ #${s.order_id}`}
              </Link>
              {s.client_name && <span className="text-muted">· {s.client_name}</span>}
              <Badge className="bg-accent-soft text-accent">score {s.score}</Badge>
              {s.reasons.length > 0 && (
                <span className="truncate text-muted">{s.reasons.join(", ")}</span>
              )}
              <Button
                className="ml-auto h-7"
                onClick={() => assign(s.order_id, s.order_label ?? `#${s.order_id}`)}
              >
                Привязать
              </Button>
            </div>
          ))}
        </div>
      )}

      <div className="mt-2.5 flex flex-wrap items-center gap-2">
        <Combobox
          value={manual}
          onChange={setManual}
          className="w-full min-w-0 flex-1 sm:w-auto sm:max-w-sm"
          placeholder="— выбрать заказ вручную —"
          searchPlaceholder="Клиент, магазин, товар…"
          options={orders.map((o) => ({
            value: String(o.id),
            label: `#${o.id} · ${o.client_name} · ${o.items}`,
            sublabel: o.store,
          }))}
        />
        <Button disabled={!manual} onClick={() => assign(Number(manual), `#${manual}`)}>
          Привязать
        </Button>
        <Button variant="ghost" onClick={dismiss}>
          Скрыть
        </Button>
      </div>
    </div>
  );
}

export default function TracksPage() {
  const qc = useQueryClient();
  const [search, setSearch] = useState("");
  const [num, setNum] = useState("");
  const [carrier, setCarrier] = useState("");

  // переход из ленты почты: /tracks?search=<номер> сразу фильтрует список
  // (window вместо useSearchParams — без Suspense-обёртки для статической страницы)
  useEffect(() => {
    const q = new URLSearchParams(window.location.search).get("search");
    if (q) setSearch(q);
  }, []);

  const { data: open } = useQuery({
    queryKey: ["tracks", "open"],
    queryFn: () => api.get<Track[]>("/api/tracks", { unmatched: true }),
  });
  const debouncedSearch = useDebounced(search.trim());
  const { data: all, isLoading } = useQuery({
    queryKey: ["tracks", "all", debouncedSearch],
    queryFn: () => api.get<Track[]>("/api/tracks", { search: debouncedSearch || undefined }),
    placeholderData: keepPreviousData,
  });
  const { data: activeOrders } = useQuery({
    queryKey: ["orders", { active: true }],
    queryFn: () => api.get<OrderListItem[]>("/api/orders", { active: true }),
  });

  const addTrack = (e: FormEvent) => {
    e.preventDefault();
    api
      .post<Track>("/api/tracks", {
        tracking_number: num.trim(),
        carrier: carrier.trim() || undefined,
      })
      .then(() => {
        setNum("");
        setCarrier("");
        toastSaved(undefined, "Трек добавлен — привяжите его к заказу");
        qc.invalidateQueries({ queryKey: ["tracks"] });
      })
      .catch((err) => toastError(err.message));
  };

  const remove = (t: Track) => {
    api
      .del(`/api/tracks/${t.id}`)
      .then(() => {
        toastSaved(undefined, "Трек удалён");
        qc.invalidateQueries({ queryKey: ["tracks"] });
      })
      .catch((err) => toastError(err.message));
  };

  return (
    <div className="space-y-4">
      <h1 className="text-[17px] font-semibold tracking-tight">Треки</h1>

      <Section title={`Непривязанные (${open?.length ?? 0})`}>
        {(open ?? []).length === 0 ? (
          <EmptyState
            title="Непривязанных треков нет"
            hint="Сюда попадают треки из писем, для которых автоматика не нашла заказ."
          />
        ) : (
          <div className="space-y-2.5">
            {(open ?? []).map((t) => (
              <OpenTrackCard key={t.id} track={t} orders={activeOrders ?? []} />
            ))}
          </div>
        )}
      </Section>

      <Section
        title="Все треки"
        actions={
          <form onSubmit={addTrack} className="flex gap-2">
            <Input
              className="w-56 font-mono"
              placeholder="Добавить трек…"
              value={num}
              onChange={(e) => setNum(e.target.value)}
            />
            <Input
              className="w-20"
              placeholder="UPS"
              value={carrier}
              onChange={(e) => setCarrier(e.target.value)}
            />
            <Button type="submit" className="h-7" disabled={!num.trim()}>
              Добавить
            </Button>
          </form>
        }
      >
        <Input
          className="mb-3 max-w-72 font-mono"
          placeholder="Поиск по номеру…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        {isLoading ? (
          <p className="py-8 text-center text-[13px] text-muted">Загрузка…</p>
        ) : (
          <div className="overflow-x-auto">
          <table className="w-full min-w-[560px]">
            <thead>
              <tr className="border-b border-line text-left text-[11.5px] tracking-wide text-muted uppercase">
                <th className="px-3 py-2 font-medium">Номер</th>
                <th className="px-3 py-2 font-medium">Перевозчик</th>
                <th className="px-3 py-2 font-medium">Заказ</th>
                <th className="px-3 py-2 font-medium">Источник</th>
                <th className="px-3 py-2" />
              </tr>
            </thead>
            <tbody>
              {(all ?? []).map((t) => (
                <tr key={t.id} className="border-b border-line/60 last:border-0">
                  <td className="px-3 py-2 font-mono text-[12.5px]">{t.tracking_number}</td>
                  <td className="px-3 py-2 text-[12.5px] text-muted uppercase">{t.carrier ?? "—"}</td>
                  <td className="px-3 py-2 text-[12.5px]">
                    {t.order_id ? (
                      <Link href={`/orders/${t.order_id}`} className="text-accent hover:underline">
                        #{t.order_id}
                      </Link>
                    ) : t.match_status === "dismissed" ? (
                      <span className="text-muted">скрыт</span>
                    ) : (
                      <span className="text-amber-600 dark:text-amber-400">непривязан</span>
                    )}
                  </td>
                  <td className="px-3 py-2 text-[12.5px] text-muted">
                    {t.source === "email" ? "письмо" : "вручную"}
                  </td>
                  <td className="px-3 py-2 text-right">
                    <Button variant="ghost" className="h-7" onClick={() => remove(t)}>
                      Удалить
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          </div>
        )}
      </Section>
    </div>
  );
}
