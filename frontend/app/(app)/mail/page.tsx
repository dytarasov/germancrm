"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { keepPreviousData, useQuery, useQueryClient } from "@tanstack/react-query";
import { useDebounced } from "@/lib/use-debounced";
import { api } from "@/lib/api";
import type {
  EmailDetail,
  EmailExtracted,
  EmailRow,
  MailEvent,
  MailHealth,
  MailReview,
  OrderListItem,
  Settings,
} from "@/lib/api-types";
import { fmtDateTime } from "@/lib/format";
import { Badge, Button, Card, EmptyState, Input, Section, Seg, Spinner, cx } from "@/components/ui";
import { SelectBox } from "@/components/select-box";
import { Combobox } from "@/components/combobox";
import { pushToast, toastError, toastSaved } from "@/components/toasts";

const ACTION_LABEL: Record<string, string> = {
  status_advanced: "статус обновлён",
  track_added: "трек добавлен",
  track_suggested: "трек ждёт привязки",
  order_no_linked: "номер заказа привязан",
  ignored_stale: "устаревшее письмо",
  ignored_terminal: "заказ уже закрыт",
  manual_review: "нужен разбор",
  info: "инфо",
};

const ACTION_DOT: Record<string, string> = {
  status_advanced: "bg-green-500",
  track_added: "bg-blue-500",
  track_suggested: "bg-amber-500",
  order_no_linked: "bg-cyan-500",
  manual_review: "bg-red-500",
};

const EVENT_RU: Record<string, string> = {
  order_confirmation: "подтверждение заказа",
  shipped: "отправлен магазином",
  arrived_at_warehouse: "поступил на склад США",
  delivery_update: "обновление доставки",
  cancellation_or_refund: "отмена / возврат",
  other: "прочее",
};

const EMAIL_STATUS: Record<string, { label: string; cls: string }> = {
  new: { label: "новое", cls: "bg-blue-500/12 text-blue-700 dark:text-blue-400" },
  pending_llm: { label: "ждёт LLM", cls: "bg-blue-500/12 text-blue-700 dark:text-blue-400" },
  processed: { label: "обработано", cls: "bg-green-500/12 text-green-700 dark:text-green-400" },
  manual_review: { label: "ручной разбор", cls: "bg-amber-500/15 text-amber-700 dark:text-amber-400" },
  poison: { label: "ошибка", cls: "bg-red-500/12 text-red-700 dark:text-red-400" },
  filtered: { label: "отфильтровано", cls: "bg-zinc-500/10 text-muted" },
  ignored: { label: "игнор", cls: "bg-zinc-500/10 text-muted" },
};

function EmailStatusChip({ status }: { status: string }) {
  const meta = EMAIL_STATUS[status] ?? { label: status, cls: "bg-zinc-500/10 text-muted" };
  return <Badge className={meta.cls}>{meta.label}</Badge>;
}

function domainOf(addr: string): string {
  return addr.split("@").pop()?.replace(/[>\s]/g, "") ?? addr;
}

function HealthBanner({ health }: { health: MailHealth }) {
  if (!health.configured)
    return (
      <Card className="p-3.5 text-[13px] text-muted">
        Чтение почты не настроено — задайте GOOGLE_OAUTH_CLIENT_ID/SECRET в .env и подключите Gmail в{" "}
        <Link href="/settings" className="text-accent hover:underline">
          настройках
        </Link>
        .
      </Card>
    );
  if (!health.gmail_connected || health.needs_reauth)
    return (
      <Card className="border-red-500/30 bg-red-500/8 p-3.5 text-[13px] font-medium text-red-700 dark:text-red-400">
        {health.needs_reauth ? "Gmail требует повторной авторизации." : "Gmail не подключён."}{" "}
        <Link href="/settings" className="underline">
          Перейти в настройки →
        </Link>
      </Card>
    );
  if (!health.worker_ok)
    return (
      <Card className="border-red-500/30 bg-red-500/8 p-3.5 text-[13px] font-medium text-red-700 dark:text-red-400">
        Почта не читается{health.last_success_at ? ` с ${fmtDateTime(health.last_success_at)}` : ""}.
      </Card>
    );
  return (
    <Card className="flex flex-wrap items-center gap-2 p-3.5 text-[13px] text-muted">
      <span className="inline-block size-1.5 rounded-full bg-green-500" />
      Почта читается · {health.gmail_email} · последняя проверка {fmtDateTime(health.last_success_at)}
      {health.llm_degraded && (
        <Badge className="ml-2 bg-amber-500/15 text-amber-700 dark:text-amber-400">
          LLM недоступен — письма копятся
        </Badge>
      )}
    </Card>
  );
}

/** Форма привязки письма к заказу (общая для очереди и журнала). */
function ResolveForm({
  emailId,
  extracted,
  onDone,
}: {
  emailId: number;
  extracted: EmailExtracted | null;
  onDone: () => void;
}) {
  const qc = useQueryClient();
  const { data: orders } = useQuery({
    queryKey: ["orders", { active: true }],
    queryFn: () => api.get<OrderListItem[]>("/api/orders", { active: true }),
  });

  const [orderId, setOrderId] = useState("");
  const [eventType, setEventType] = useState("");
  const [tracks, setTracks] = useState<{ number: string; checked: boolean }[]>([]);
  const [manualTrack, setManualTrack] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!extracted) return;
    const uniq = [...new Set(extracted.tracking_numbers.map((t) => t.number))];
    setTracks(uniq.map((n) => ({ number: n, checked: true })));
    if (extracted.event_type === "shipped" || extracted.event_type === "arrived_at_warehouse")
      setEventType(extracted.event_type);
  }, [extracted]);

  const addManual = () => {
    const v = manualTrack.trim();
    if (!v) return;
    setTracks((ts) => (ts.some((t) => t.number === v) ? ts : [...ts, { number: v, checked: true }]));
    setManualTrack("");
  };

  const apply = () => {
    setBusy(true);
    api
      .post(`/api/mail/emails/${emailId}/resolve`, {
        order_id: Number(orderId),
        event_type: eventType || null,
        tracking_numbers: tracks.filter((t) => t.checked).map((t) => t.number),
        carrier: extracted?.carrier ?? null,
      })
      .then(() => {
        toastSaved(undefined, "Письмо разобрано");
        for (const key of [
          "mail-review",
          "mail-events",
          "mail-health",
          "mail-log",
          "mail-email",
          "mail-email-events",
          "dashboard",
          "orders",
          "order",
          "client",
          "tracks",
        ])
          qc.invalidateQueries({ queryKey: [key] });
        onDone();
      })
      .catch((e) => toastError(e.message))
      .finally(() => setBusy(false));
  };

  return (
    <div className="space-y-3">
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <div className="space-y-1.5">
          <div className="text-[12px] font-medium text-muted">Заказ</div>
          <Combobox
            className="w-full"
            value={orderId}
            onChange={setOrderId}
            placeholder="— выберите заказ —"
            searchPlaceholder="Клиент, магазин, товар, номер…"
            options={(orders ?? []).map((o) => ({
              value: String(o.id),
              label: `#${o.id} · ${o.client_name} · ${o.items}`,
              sublabel: `${o.store}${o.store_order_number ? ` · ${o.store_order_number}` : ""}`,
            }))}
          />
        </div>
        <div className="space-y-1.5">
          <div className="text-[12px] font-medium text-muted">Событие</div>
          <SelectBox
            className="w-full"
            value={eventType}
            onChange={setEventType}
            options={[
              { value: "", label: "Не менять статус" },
              { value: "shipped", label: "Отправлен магазином" },
              { value: "arrived_at_warehouse", label: "Поступил на склад США" },
            ]}
          />
          <p className="text-[11.5px] text-muted">
            Статус двигается только вперёд; устаревшее событие безопасно игнорируется.
          </p>
        </div>
      </div>

      <div className="space-y-1.5">
        <div className="text-[12px] font-medium text-muted">
          Треки
          {tracks.length > 0 && ` (${tracks.filter((t) => t.checked).length} из ${tracks.length})`}
        </div>
        {tracks.map((t) => (
          <label key={t.number} className="flex min-h-8 items-center gap-2 text-[12.5px]">
            <input
              type="checkbox"
              checked={t.checked}
              onChange={(e) =>
                setTracks((ts) =>
                  ts.map((x) => (x.number === t.number ? { ...x, checked: e.target.checked } : x)),
                )
              }
            />
            <span className="font-mono break-all">{t.number}</span>
          </label>
        ))}
        <div className="flex flex-wrap gap-2">
          <Input
            className="font-mono sm:max-w-72"
            placeholder="Добавить трек вручную…"
            value={manualTrack}
            onChange={(e) => setManualTrack(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                addManual();
              }
            }}
          />
          <Button type="button" onClick={addManual} disabled={!manualTrack.trim()}>
            Добавить
          </Button>
        </div>
      </div>

      <Button
        variant="primary"
        className="h-11 w-full sm:h-8 sm:w-auto"
        disabled={!orderId || busy}
        onClick={apply}
      >
        {busy ? "Применяю…" : "Применить"}
      </Button>
    </div>
  );
}

/**
 * Общая панель раскрытия письма: текст, «LLM увидел», события по письму,
 * форма разбора (если разрешена). Детали грузятся лениво — только при раскрытии.
 */
function EmailPanel({
  emailId,
  allowResolve,
  showEvents,
  onDone,
}: {
  emailId: number;
  allowResolve: boolean;
  showEvents: boolean;
  onDone: () => void;
}) {
  const { data: detail, isLoading } = useQuery({
    queryKey: ["mail-email", emailId],
    queryFn: () => api.get<EmailDetail>(`/api/mail/emails/${emailId}`),
  });
  const { data: emailEvents } = useQuery({
    queryKey: ["mail-email-events", emailId],
    queryFn: () => api.get<MailEvent[]>(`/api/mail/emails/${emailId}/events`),
    enabled: showEvents,
  });

  if (isLoading || !detail)
    return (
      <div className="py-3 text-center">
        <Spinner />
      </div>
    );

  const ex = detail.extracted;

  return (
    <div className="space-y-3 pt-3">
      {ex && (
        <div className="space-y-1">
          <div className="flex flex-wrap items-center gap-x-1.5 gap-y-1 rounded-md bg-accent-soft px-2.5 py-1.5 text-[12px]">
            <span className="font-medium text-accent">LLM увидел:</span>
            <span>
              {EVENT_RU[ex.event_type] ?? ex.event_type} ({Math.round(ex.confidence * 100)}%)
            </span>
            {ex.order_number && (
              <span>
                · заказ <span className="font-mono">{ex.order_number}</span>
              </span>
            )}
            {ex.tracking_numbers.length > 0 && (
              <span className="break-all">
                · треки:{" "}
                <span className="font-mono">
                  {[...new Set(ex.tracking_numbers.map((t) => t.number))].join(", ")}
                </span>
              </span>
            )}
          </div>
          {ex.reasoning && (
            <p className="px-2.5 text-[12px] text-muted">Почему: {ex.reasoning}</p>
          )}
        </div>
      )}

      {detail.body_text && (
        <pre className="max-h-56 overflow-y-auto rounded-md bg-surface2/60 p-2.5 font-mono text-[11.5px] leading-relaxed break-words whitespace-pre-wrap text-muted">
          {detail.body_text}
        </pre>
      )}

      {showEvents && (
        <div className="space-y-1">
          <div className="text-[12px] font-medium text-muted">События по письму</div>
          {(emailEvents ?? []).length === 0 ? (
            <p className="text-[12px] text-muted">С этим письмом пока ничего не сделано.</p>
          ) : (
            (emailEvents ?? []).map((ev) => (
              <div key={ev.id} className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5 text-[12.5px]">
                <span className="text-[11.5px] text-muted">{fmtDateTime(ev.created_at)}</span>
                <span className="text-[11px] tracking-wide text-muted uppercase">
                  {ACTION_LABEL[ev.action] ?? ev.action}
                </span>
                {ev.summary && <span>{ev.summary}</span>}
                {ev.order_id && (
                  <Link href={`/orders/${ev.order_id}`} className="text-accent hover:underline">
                    {ev.order_label ?? `заказ #${ev.order_id}`}
                  </Link>
                )}
              </div>
            ))
          )}
        </div>
      )}

      {allowResolve && (
        <div className="border-t border-line pt-3">
          <ResolveForm emailId={emailId} extracted={ex} onDone={onDone} />
        </div>
      )}
    </div>
  );
}

/** Карточка письма в очереди разбора / секции «Отфильтровано». */
function EmailCard({
  e,
  showError,
  filtered,
  onWhitelist,
}: {
  e: EmailRow;
  showError?: boolean;
  filtered?: boolean;
  onWhitelist?: (fromAddr: string) => void;
}) {
  const qc = useQueryClient();
  const [resolving, setResolving] = useState(false);

  const act = (verb: "retry" | "ignore", msg: string) => {
    api
      .post(`/api/mail/emails/${e.id}/${verb}`)
      .then(() => {
        toastSaved(undefined, msg);
        qc.invalidateQueries({ queryKey: ["mail-review"] });
        qc.invalidateQueries({ queryKey: ["mail-health"] });
        qc.invalidateQueries({ queryKey: ["mail-log"] });
      })
      .catch((err) => toastError(err.message));
  };

  return (
    <div className="rounded-lg border border-line p-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="min-w-0 truncate text-[13px] font-medium">{e.subject ?? "(без темы)"}</span>
        <EmailStatusChip status={e.processing_status} />
        <span className="ml-auto shrink-0 text-[11.5px] text-muted">{fmtDateTime(e.sent_at)}</span>
      </div>
      <div className="mt-0.5 text-[12px] text-muted">{e.from_addr}</div>
      {!resolving && e.snippet && (
        <div className="mt-1 line-clamp-2 text-[12px] text-muted">{e.snippet}</div>
      )}
      {showError && e.error && (
        <div className="mt-1.5 rounded bg-red-500/8 px-2 py-1 font-mono text-[11.5px] break-words text-red-700 dark:text-red-400">
          {e.error}
        </div>
      )}
      <div className="mt-2 flex flex-wrap gap-1.5">
        <Button className="h-9 sm:h-7" onClick={() => setResolving((v) => !v)}>
          {resolving ? "Свернуть" : "Разобрать"}
        </Button>
        {filtered ? (
          <>
            <Button
              className="h-9 sm:h-7"
              onClick={() => act("retry", "Письмо уйдёт в LLM при следующем цикле")}
            >
              Прогнать через LLM
            </Button>
            {onWhitelist && (
              <Button
                variant="ghost"
                className="h-9 sm:h-7"
                onClick={() => onWhitelist(e.from_addr)}
              >
                Добавить домен в whitelist
              </Button>
            )}
          </>
        ) : (
          <>
            <Button className="h-9 sm:h-7" onClick={() => act("retry", "Письмо отправлено на переобработку")}>
              Повторить
            </Button>
            <Button
              variant="ghost"
              className="h-9 sm:h-7"
              onClick={() => act("ignore", "Письмо проигнорировано")}
            >
              Игнорировать
            </Button>
          </>
        )}
      </div>
      {resolving && (
        <EmailPanel
          emailId={e.id}
          allowResolve
          showEvents={false}
          onDone={() => setResolving(false)}
        />
      )}
    </div>
  );
}

const LOG_FILTERS: { value: string; label: string }[] = [
  { value: "", label: "Все" },
  { value: "processed", label: "Обработано" },
  { value: "manual_review", label: "Ручной разбор" },
  { value: "pending_llm", label: "Ждут LLM" },
  { value: "filtered", label: "Отфильтровано" },
  { value: "ignored", label: "Игнор" },
  { value: "poison", label: "Ошибка" },
];

/** Строка журнала: клик раскрывает детали, события и действия по статусу. */
function JournalRow({ e }: { e: EmailRow }) {
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const processed = e.processing_status === "processed";

  const act = (verb: "retry" | "ignore", msg: string) => {
    api
      .post(`/api/mail/emails/${e.id}/${verb}`)
      .then(() => {
        toastSaved(undefined, msg);
        qc.invalidateQueries({ queryKey: ["mail-log"] });
        qc.invalidateQueries({ queryKey: ["mail-review"] });
        qc.invalidateQueries({ queryKey: ["mail-health"] });
      })
      .catch((err) => toastError(err.message));
  };

  return (
    <div className={cx("rounded-lg border border-line", open && "bg-surface2/30")}>
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex w-full flex-wrap items-center gap-x-2.5 gap-y-1 px-3 py-2.5 text-left"
      >
        <span className="w-26 shrink-0 text-[11.5px] text-muted">{fmtDateTime(e.sent_at)}</span>
        <span className="w-32 shrink-0 truncate font-mono text-[11.5px] text-muted">
          {domainOf(e.from_addr)}
        </span>
        <span className="min-w-0 flex-1 truncate text-[13px] font-medium">
          {e.subject ?? "(без темы)"}
        </span>
        <EmailStatusChip status={e.processing_status} />
        {e.event_type && (
          <span className="shrink-0 text-[11.5px] text-muted">
            {EVENT_RU[e.event_type] ?? e.event_type}
            {e.confidence !== null && ` · ${Math.round(e.confidence * 100)}%`}
          </span>
        )}
      </button>

      {open && (
        <div className="border-t border-line px-3 pb-3">
          {!processed && (
            <div className="flex flex-wrap gap-1.5 pt-3">
              <Button className="h-9 sm:h-7" onClick={() => act("retry", "Письмо отправлено на переобработку")}>
                Повторить
              </Button>
              <Button
                variant="ghost"
                className="h-9 sm:h-7"
                onClick={() => act("ignore", "Письмо проигнорировано")}
              >
                Игнорировать
              </Button>
            </div>
          )}
          <EmailPanel
            emailId={e.id}
            allowResolve={!processed}
            showEvents
            onDone={() => setOpen(false)}
          />
        </div>
      )}
    </div>
  );
}

function JournalTab() {
  const [status, setStatus] = useState("");
  const [search, setSearch] = useState("");
  const debouncedSearch = useDebounced(search.trim());

  const { data: rows, isLoading } = useQuery({
    queryKey: ["mail-log", status, debouncedSearch],
    queryFn: () =>
      api.get<EmailRow[]>("/api/mail/emails", {
        status: status || undefined,
        search: debouncedSearch || undefined,
        limit: 100,
      }),
    placeholderData: keepPreviousData,
  });

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-1.5">
        {LOG_FILTERS.map((f) => (
          <button
            key={f.value}
            onClick={() => setStatus(f.value)}
            className={cx(
              "h-8 rounded-full border px-3 text-[12.5px] font-medium transition-colors sm:h-7",
              status === f.value
                ? "border-accent/40 bg-accent-soft text-accent"
                : "border-line text-muted hover:bg-surface2 hover:text-ink",
            )}
          >
            {f.label}
          </button>
        ))}
        <Input
          className="w-full sm:ml-auto sm:max-w-64"
          placeholder="Поиск: отправитель, тема, домен…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
      </div>

      {isLoading ? (
        <p className="py-8 text-center text-[13px] text-muted">Загрузка…</p>
      ) : (rows ?? []).length === 0 ? (
        <EmptyState title="Писем не найдено" hint="Поменяйте фильтр или дождитесь следующей проверки почты." />
      ) : (
        <div className="space-y-2">
          {(rows ?? []).map((e) => (
            <JournalRow key={e.id} e={e} />
          ))}
        </div>
      )}
    </div>
  );
}

type Tab = "review" | "log" | "events";

export default function MailPage() {
  const qc = useQueryClient();
  const [tab, setTab] = useState<Tab>("review");
  const [showFiltered, setShowFiltered] = useState(false);

  const { data: health } = useQuery({
    queryKey: ["mail-health"],
    queryFn: () => api.get<MailHealth>("/api/mail/health"),
    refetchInterval: 30_000,
  });
  const { data: events } = useQuery({
    queryKey: ["mail-events"],
    queryFn: () => api.get<MailEvent[]>("/api/mail/events", { limit: 50 }),
    refetchInterval: 60_000,
    enabled: tab === "events",
  });
  const { data: review } = useQuery({
    queryKey: ["mail-review"],
    queryFn: () => api.get<MailReview>("/api/mail/review"),
    refetchInterval: 60_000,
  });

  const poll = () => {
    api
      .post("/api/mail/poll")
      .then(() => pushToast({ title: "Проверяю почту…", kind: "ok" }))
      .catch((e) => toastError(e.message));
    setTimeout(() => {
      qc.invalidateQueries({ queryKey: ["mail-events"] });
      qc.invalidateQueries({ queryKey: ["mail-review"] });
      qc.invalidateQueries({ queryKey: ["mail-health"] });
      qc.invalidateQueries({ queryKey: ["mail-log"] });
    }, 5000);
  };

  const addToWhitelist = async (fromAddr: string) => {
    const domain = domainOf(fromAddr).toLowerCase();
    if (!domain) return;
    try {
      const s = await api.get<Settings>("/api/settings");
      if (!s.whitelist_domains.includes(domain)) {
        await api.patch("/api/settings", { whitelist_domains: [...s.whitelist_domains, domain] });
      }
      toastSaved(undefined, `Домен ${domain} добавлен в whitelist`);
      qc.invalidateQueries({ queryKey: ["settings"] });
    } catch (e) {
      toastError(e instanceof Error ? e.message : "Ошибка");
    }
  };

  const needReview = review?.emails ?? [];
  const filtered = review?.filtered ?? [];

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-[17px] font-semibold tracking-tight">Почта</h1>
        <Button onClick={poll} disabled={!health?.gmail_connected}>
          Проверить сейчас
        </Button>
      </div>

      {health && <HealthBanner health={health} />}

      <Seg
        value={tab}
        onChange={setTab}
        options={[
          { value: "review", label: needReview.length > 0 ? `Разбор (${needReview.length})` : "Разбор" },
          { value: "log", label: "Журнал" },
          { value: "events", label: "Лента" },
        ]}
      />

      {tab === "review" && (
        <>
          {(review?.open_tracks.length ?? 0) > 0 && (
            <Card className="flex flex-wrap items-center justify-between gap-2 p-3.5 text-[13px]">
              <span>
                Треков без заказа: <b>{review?.open_tracks.length}</b>
              </span>
              <Link href="/tracks" className="text-accent hover:underline">
                Разобрать на странице «Треки» →
              </Link>
            </Card>
          )}

          {needReview.length === 0 ? (
            <Card>
              <EmptyState
                title="Очередь разбора пуста"
                hint="Письма, с которыми автоматика не справилась, будут ждать вас здесь."
              />
            </Card>
          ) : (
            <Section title={`Требует разбора (${needReview.length})`}>
              <div className="space-y-2.5">
                {needReview.map((e) => (
                  <EmailCard key={e.id} e={e} showError />
                ))}
              </div>
            </Section>
          )}

          <Card className="p-3.5">
            <button
              onClick={() => setShowFiltered((v) => !v)}
              className="flex w-full items-center justify-between text-[13px] font-medium"
            >
              Отфильтровано ({filtered.length})
              <span className="text-muted">{showFiltered ? "свернуть" : "показать"}</span>
            </button>
            {showFiltered && (
              <div className="mt-3 space-y-2.5">
                {filtered.length === 0 ? (
                  <p className="text-[12.5px] text-muted">Пусто</p>
                ) : (
                  filtered.map((e) => (
                    <EmailCard key={e.id} e={e} filtered onWhitelist={addToWhitelist} />
                  ))
                )}
              </div>
            )}
          </Card>
        </>
      )}

      {tab === "log" && <JournalTab />}

      {tab === "events" && (
        <Section title="Лента событий">
          {(events ?? []).length === 0 ? (
            <EmptyState
              title="Событий пока нет"
              hint="Когда придут письма от магазинов, здесь появится, что автоматика с ними сделала."
            />
          ) : (
            <ul className="space-y-1">
              {(events ?? []).map((ev) => (
                <li
                  key={ev.id}
                  className="flex items-baseline gap-2.5 rounded px-1.5 py-1.5 text-[13px] hover:bg-surface2/50"
                >
                  <span
                    className={
                      "mt-1 inline-block size-1.5 shrink-0 self-center rounded-full " +
                      (ACTION_DOT[ev.action] ?? "bg-zinc-400")
                    }
                  />
                  <span className="w-30 shrink-0 text-[11.5px] text-muted">
                    {fmtDateTime(ev.created_at)}
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="mr-1.5 text-[11.5px] text-muted uppercase">
                      {ACTION_LABEL[ev.action] ?? ev.action}
                    </span>
                    {ev.summary ?? ev.subject ?? ev.from_addr}
                    {ev.order_id && (
                      <Link
                        href={`/orders/${ev.order_id}`}
                        className="ml-1.5 text-accent hover:underline"
                      >
                        {ev.order_label ?? `заказ #${ev.order_id}`}
                      </Link>
                    )}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </Section>
      )}
    </div>
  );
}
