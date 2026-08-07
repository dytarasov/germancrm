"use client";

import { FormEvent, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "@/lib/api";
import type { Flight, OrderDetail, OrderItem, OrderStatus, Payment, Track } from "@/lib/api-types";
import { STATUS_LABEL, isTerminal } from "@/lib/status";
import { fmtDate, fmtDateTime, fmtMoney, isoToday, safeHref } from "@/lib/format";
import { Badge, Button, Card, Field, Input, Section, Spinner, cx } from "@/components/ui";
import { Combobox } from "@/components/combobox";
import { DatePicker, formatDateRu } from "@/components/date-picker";
import { RouteStepper } from "@/components/route-stepper";
import { StatusBadge, OverdueBadge } from "@/components/status-badge";
import { InlineField } from "@/components/inline-field";
import { pushToast, toastError, toastSaved } from "@/components/toasts";

export default function OrderPage() {
  const { id } = useParams<{ id: string }>();
  const orderId = Number(id);
  const router = useRouter();
  const qc = useQueryClient();

  const [commissionFlash, setCommissionFlash] = useState(false);
  const [refundOpen, setRefundOpen] = useState(false);
  const [refundAmount, setRefundAmount] = useState("");
  const [refundCommission, setRefundCommission] = useState("");

  const { data: order, isLoading } = useQuery({
    queryKey: ["order", orderId],
    queryFn: () => api.get<OrderDetail>(`/api/orders/${orderId}`),
  });
  const { data: flights } = useQuery({
    queryKey: ["flights"],
    queryFn: () => api.get<Flight[]>("/api/flights"),
  });

  const apply = (d: OrderDetail) => {
    qc.setQueryData(["order", orderId], d);
    qc.invalidateQueries({ queryKey: ["orders"] });
    qc.invalidateQueries({ queryKey: ["dashboard"] });
    qc.invalidateQueries({ queryKey: ["clients"] });
    qc.invalidateQueries({ queryKey: ["client"] });
  };

  const patch = useMutation<OrderDetail, ApiError, Record<string, unknown>>({
    mutationFn: (body) => api.patch<OrderDetail>(`/api/orders/${orderId}`, body),
    onSuccess: apply,
    onError: (e) => toastError(e.message),
  });

  const statusMut = useMutation<OrderDetail, ApiError, OrderStatus>({
    mutationFn: (status) => api.post<OrderDetail>(`/api/orders/${orderId}/status`, { status }),
    onSuccess: apply,
    onError: (e) => toastError(e.message),
  });

  const closeMut = useMutation<OrderDetail, ApiError, void>({
    mutationFn: () => api.post<OrderDetail>(`/api/orders/${orderId}/close`, {}),
    onSuccess: apply,
    onError: (e) => {
      if (e.code === "commission_required") {
        setCommissionFlash(true);
        setTimeout(() => setCommissionFlash(false), 2500);
        toastError("Сначала заполните комиссию — без неё заказ не закрывается");
      } else {
        toastError(e.message);
      }
    },
  });

  if (isLoading || !order)
    return <p className="py-16 text-center text-[13px] text-muted">Загрузка…</p>;

  const prevStatus = order.status;
  const saveField = (field: string, v: unknown, old: unknown) => {
    patch.mutate(
      { [field]: v },
      { onSuccess: () => toastSaved(() => patch.mutate({ [field]: old })) },
    );
  };

  // Откат к прежнему статусу: терминальные нельзя выставить через POST /status —
  // используем их собственные эндпоинты (для refund — с прежними суммами из снапшота).
  const revertTo = (from: OrderStatus, snap: OrderDetail) => {
    if (from === "cancelled") {
      api
        .post<OrderDetail>(`/api/orders/${orderId}/cancel`, {})
        .then(apply)
        .catch((e) => toastError(e.message));
    } else if (from === "refunded") {
      api
        .post<OrderDetail>(`/api/orders/${orderId}/refund`, {
          refunded_amount_usd: snap.refunded_amount_usd,
          commission_usd: snap.commission_usd,
        })
        .then(apply)
        .catch((e) => toastError(e.message));
    } else if (from === "closed") {
      closeMut.mutate();
    } else {
      statusMut.mutate(from);
    }
  };

  const setStatus = (next: OrderStatus) => {
    const from = prevStatus;
    const snap = order;
    if (next === "closed") {
      closeMut.mutate(undefined, {
        onSuccess: () => toastSaved(() => revertTo(from, snap), "Заказ закрыт"),
      });
    } else {
      statusMut.mutate(next, {
        onSuccess: () =>
          toastSaved(() => revertTo(from, snap), `Статус: ${STATUS_LABEL[next]}`),
      });
    }
  };

  const cancel = () => {
    const from = prevStatus;
    const snap = order;
    api
      .post<OrderDetail>(`/api/orders/${orderId}/cancel`, {})
      .then((d) => {
        apply(d);
        toastSaved(() => revertTo(from, snap), "Заказ отменён");
      })
      .catch((e) => toastError(e.message));
  };

  const copy = () => {
    api
      .post<OrderDetail>(`/api/orders/${orderId}/copy`, {})
      .then((d) => {
        qc.invalidateQueries({ queryKey: ["orders"] });
        pushToast({ title: `Копия создана — заказ #${d.id}`, kind: "ok" });
        router.push(`/orders/${d.id}`);
      })
      .catch((e) => toastError(e.message));
  };

  const refund = (e: FormEvent) => {
    e.preventDefault();
    const from = prevStatus;
    const snap = order;
    api
      .post<OrderDetail>(`/api/orders/${orderId}/refund`, {
        refunded_amount_usd: refundAmount.trim(),
        commission_usd: refundCommission.trim() === "" ? undefined : refundCommission.trim(),
      })
      .then((d) => {
        apply(d);
        setRefundOpen(false);
        // Полный откат возврата: прежний статус + прежняя комиссия.
        toastSaved(() => {
          api
            .post<OrderDetail>(`/api/orders/${orderId}/status`, { status: from })
            .then(() =>
              api.patch<OrderDetail>(`/api/orders/${orderId}`, {
                commission_usd: snap.commission_usd,
              }),
            )
            .then(apply)
            .catch((err) => toastError(err.message));
        }, "Возврат оформлен");
      })
      .catch((err) => toastError(err.message));
  };

  const weight = order.weight_kg ? parseFloat(order.weight_kg) : null;
  const commissionHint =
    weight && order.commission_usd === null
      ? `Подсказка: ${weight} кг × $50 = $${(weight * 50).toFixed(2)}`
      : undefined;

  const saving = patch.isPending || statusMut.isPending || closeMut.isPending;

  return (
    <div className="space-y-4">
      {/* Шапка */}
      <div className="flex flex-wrap items-start justify-between gap-x-4 gap-y-1">
        <div className="min-w-0">
          <div className="flex items-center gap-2 text-[12.5px] text-muted">
            <Link href="/orders" className="hover:text-ink">
              Заказы
            </Link>
            <span>/</span>
            <Link href={`/clients/${order.client_id}`} className="hover:text-accent hover:underline">
              {order.client_name}
            </Link>
            <span>·</span>
            <span>{order.store}</span>
          </div>
          <div className="mt-1 flex flex-wrap items-center gap-x-2.5 gap-y-1">
            <h1 className="truncate text-[17px] font-semibold tracking-tight">
              #{order.id} · {order.items}
            </h1>
            <StatusBadge status={order.status} />
            {order.is_overdue && <OverdueBadge />}
            {order.copied_from && (
              <Link
                href={`/orders/${order.copied_from}`}
                className="text-[12px] text-muted hover:text-accent"
              >
                копия #{order.copied_from}
              </Link>
            )}
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-1.5 pt-1 text-[12px] text-muted">
          {saving ? (
            <>
              <Spinner /> Сохраняю…
            </>
          ) : (
            <>
              <span className="inline-block size-1.5 rounded-full bg-green-500" /> Сохранено
            </>
          )}
        </div>
      </div>

      {/* Маршрут */}
      <Card className="p-3">
        <RouteStepper status={order.status} onSelect={setStatus} busy={saving} />
        {isTerminal(order.status) && order.status !== "closed" && (
          <div className="mt-2 flex flex-wrap items-center gap-2 px-1.5">
            <StatusBadge status={order.status} />
            <span className="text-[12.5px] text-muted">
              {order.status === "cancelled"
                ? "Заказ отменён — вернуть в работу можно кликом по сегменту после смены статуса вручную ниже."
                : `Возврат ${fmtMoney(order.refunded_amount_usd)} оформлен ${fmtDateTime(order.refunded_at)}.`}
            </span>
            <Button variant="ghost" className="ml-auto" onClick={() => setStatus("purchased")}>
              Вернуть в работу
            </Button>
          </div>
        )}
      </Card>

      <div className="grid grid-cols-1 gap-3 lg:grid-cols-3">
        {/* Поля */}
        <Card className="grid grid-cols-1 gap-x-4 gap-y-3 p-4 sm:grid-cols-2 lg:col-span-2">
          <InlineField
            label="Товар"
            value={order.items}
            onSave={(v) => v && saveField("items", v, order.items)}
          />
          <InlineField
            label="Магазин"
            value={order.store}
            onSave={(v) => v && saveField("store", v, order.store)}
          />
          <InlineField
            label="Номер заказа в магазине"
            value={order.store_order_number}
            mono
            placeholder="необязательно"
            onSave={(v) => saveField("store_order_number", v, order.store_order_number)}
          />
          <InlineField
            label="Цена закупки, $"
            value={order.purchase_price_usd}
            type="money"
            onSave={(v) => v && saveField("purchase_price_usd", v, order.purchase_price_usd)}
          />
          <div
            className={cx(
              "rounded-md transition-shadow",
              commissionFlash && "ring-2 ring-amber-500/60",
            )}
          >
            <InlineField
              label="Комиссия, $ (пусто = ещё не знаю, 0 = без наценки)"
              value={order.commission_usd}
              type="money"
              placeholder="не задана"
              hint={commissionHint}
              onSave={(v) => saveField("commission_usd", v, order.commission_usd)}
            />
          </div>
          <div>
            <InlineField
              label="Вес, кг"
              value={order.weight_kg}
              type="number"
              placeholder="не взвешен"
              onSave={(v) => saveField("weight_kg", v, order.weight_kg)}
            />
            <label className="mt-1 flex items-center gap-1.5 px-2 text-[12px] text-muted">
              <input
                type="checkbox"
                checked={order.weight_is_final}
                onChange={(e) => saveField("weight_is_final", e.target.checked, order.weight_is_final)}
              />
              вес финальный
            </label>
          </div>
          <div>
            <div className="mb-0.5 px-2 text-[11.5px] font-medium text-muted">Обещанная дата</div>
            <DatePicker
              className="w-full"
              clearable
              value={order.promised_date}
              onChange={(v) => saveField("promised_date", v, order.promised_date)}
            />
          </div>
          <div>
            <div className="mb-0.5 px-2 text-[11.5px] font-medium text-muted">Дата покупки</div>
            <DatePicker
              className="w-full"
              value={order.purchased_on}
              onChange={(v) => v && saveField("purchased_on", v, order.purchased_on)}
            />
          </div>
          <div>
            <div className="mb-0.5 px-2 text-[11.5px] font-medium text-muted">Рейс</div>
            <Combobox
              className="w-full"
              value={order.flight_id ? String(order.flight_id) : ""}
              onChange={(v) => saveField("flight_id", v ? Number(v) : null, order.flight_id)}
              placeholder="Без рейса"
              searchPlaceholder="Дата или описание…"
              options={[
                { value: "", label: "Без рейса" },
                ...(flights ?? []).map((f) => ({
                  value: String(f.id),
                  label: `${formatDateRu(f.departed_on)} · ${fmtMoney(f.cost_usd)}${
                    f.description ? ` · ${f.description}` : ""
                  }`,
                })),
              ]}
            />
          </div>
          <div className="sm:col-span-2">
            <InlineField
              label="Комментарий"
              value={order.comment}
              multiline
              onSave={(v) => saveField("comment", v, order.comment)}
            />
          </div>
        </Card>

        {/* Финансы + действия */}
        <div className="space-y-3">
          <Card className="space-y-2 p-4">
            <Row k="Выручка" v={fmtMoney(order.finance.revenue_usd)} />
            <Row k="Оплачено" v={fmtMoney(order.finance.paid_usd)} />
            <div className="border-t border-line pt-2">
              <Row
                k="Остаток к доплате"
                v={order.finance.due_usd === null ? "нет комиссии" : fmtMoney(order.finance.due_usd)}
                strong
              />
            </div>
            {order.status === "refunded" && (
              <Row k="Возвращено" v={fmtMoney(order.refunded_amount_usd)} />
            )}
          </Card>

          <Card className="space-y-1.5 p-3">
            {order.status !== "closed" && !isTerminal(order.status) && (
              <Button
                variant="primary"
                className="h-11 w-full lg:h-8"
                onClick={() => setStatus("closed")}
              >
                Закрыть заказ
              </Button>
            )}
            <Button variant="outline" className="h-11 w-full lg:h-8" onClick={copy}>
              Создать копию
            </Button>
            {!isTerminal(order.status) && (
              <>
                <Button variant="danger" className="h-11 w-full lg:h-8" onClick={cancel}>
                  Отменить заказ
                </Button>
                <Button
                  variant="danger"
                  className="h-11 w-full lg:h-8"
                  onClick={() => setRefundOpen((v) => !v)}
                >
                  Возврат…
                </Button>
              </>
            )}
            {refundOpen && (
              <form onSubmit={refund} className="space-y-2 rounded-md border border-line p-2.5">
                <Field label="Возвращено, $">
                  <Input
                    autoFocus
                    inputMode="decimal"
                    className="font-mono"
                    value={refundAmount}
                    onChange={(e) => setRefundAmount(e.target.value)}
                  />
                </Field>
                <Field label="Новая комиссия, $ (пусто — не менять)">
                  <Input
                    inputMode="decimal"
                    className="font-mono"
                    value={refundCommission}
                    onChange={(e) => setRefundCommission(e.target.value)}
                  />
                </Field>
                <Button
                  type="submit"
                  variant="primary"
                  className="h-11 w-full lg:h-8"
                  disabled={!refundAmount.trim()}
                >
                  Оформить возврат
                </Button>
              </form>
            )}
          </Card>
        </div>
      </div>

      <ItemsSection order={order} />
      <TracksSection order={order} />
      <PaymentsSection order={order} />

      <Section title="История статусов">
        {order.history.length === 0 ? (
          <p className="text-[12.5px] text-muted">Пока пусто</p>
        ) : (
          <ul className="space-y-1.5">
            {order.history.map((h) => (
              <li key={h.id} className="flex items-baseline gap-2.5 text-[12.5px]">
                <span className="w-32 shrink-0 text-muted">{fmtDateTime(h.changed_at)}</span>
                <Badge
                  className={
                    h.source === "auto"
                      ? "bg-accent-soft text-accent"
                      : "bg-zinc-500/10 text-muted"
                  }
                >
                  {h.source === "auto" ? "авто" : "вручную"}
                </Badge>
                <span>
                  {h.old_status ? `${STATUS_LABEL[h.old_status]} → ` : ""}
                  <span className="font-medium">{STATUS_LABEL[h.new_status]}</span>
                </span>
                {h.comment && <span className="text-muted">— {h.comment}</span>}
              </li>
            ))}
          </ul>
        )}
      </Section>
    </div>
  );
}

function Row({ k, v, strong }: { k: string; v: string; strong?: boolean }) {
  return (
    <div className="flex items-baseline justify-between">
      <span className="text-[12.5px] text-muted">{k}</span>
      <span className={cx("font-mono text-[13px] tnum", strong && "text-[14px] font-semibold")}>
        {v}
      </span>
    </div>
  );
}

function itemDomain(url: string | null): string {
  if (!url) return "(без названия)";
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}

function ItemEditRow({
  orderId,
  item,
  onDone,
  onCancel,
}: {
  orderId: number;
  item: OrderItem;
  onDone: () => void;
  onCancel: () => void;
}) {
  const [title, setTitle] = useState(item.title ?? "");
  const [url, setUrl] = useState(item.url ?? "");
  const [qty, setQty] = useState(String(item.quantity));
  const [note, setNote] = useState(item.note ?? "");

  const save = (e: FormEvent) => {
    e.preventDefault();
    const old = item;
    api
      .patch<OrderItem>(`/api/orders/${orderId}/items/${item.id}`, {
        title: title.trim() || null,
        url: url.trim() || null,
        quantity: Math.max(1, parseInt(qty, 10) || 1),
        note: note.trim() || null,
      })
      .then(() => {
        toastSaved(() =>
          api
            .patch(`/api/orders/${orderId}/items/${item.id}`, {
              title: old.title,
              url: old.url,
              quantity: old.quantity,
              note: old.note,
            })
            .then(onDone),
        );
        onDone();
      })
      .catch((err) => toastError(err.message));
  };

  return (
    <form onSubmit={save} className="flex flex-wrap items-center gap-2 rounded-md border border-line p-2">
      <Input
        className="sm:max-w-52"
        placeholder="Название"
        value={title}
        onChange={(e) => setTitle(e.target.value)}
      />
      <Input
        className="font-mono sm:max-w-64"
        placeholder="https://…"
        value={url}
        onChange={(e) => setUrl(e.target.value)}
      />
      <Input
        className="w-16 font-mono"
        inputMode="numeric"
        aria-label="Количество"
        value={qty}
        onChange={(e) => setQty(e.target.value)}
      />
      <Input
        className="sm:max-w-44"
        placeholder="Заметка"
        value={note}
        onChange={(e) => setNote(e.target.value)}
      />
      <span className="flex gap-1">
        <Button type="submit" variant="primary" disabled={!title.trim() && !url.trim()}>
          Сохранить
        </Button>
        <Button type="button" variant="ghost" onClick={onCancel}>
          Отмена
        </Button>
      </span>
    </form>
  );
}

function ItemsSection({ order }: { order: OrderDetail }) {
  const qc = useQueryClient();
  const [title, setTitle] = useState("");
  const [url, setUrl] = useState("");
  const [qty, setQty] = useState("1");
  const [editingId, setEditingId] = useState<number | null>(null);

  // Инвалидация вместо ручного GET+apply — Query сам рефетчит последним, без гонок.
  const reload = () => qc.invalidateQueries({ queryKey: ["order", order.id] });

  const add = (e: FormEvent) => {
    e.preventDefault();
    api
      .post<OrderItem>(`/api/orders/${order.id}/items`, {
        title: title.trim() || undefined,
        url: url.trim() || undefined,
        quantity: Math.max(1, parseInt(qty, 10) || 1),
      })
      .then(() => {
        setTitle("");
        setUrl("");
        setQty("1");
        toastSaved(undefined, "Позиция добавлена");
        reload();
      })
      .catch((err) => toastError(err.message));
  };

  const remove = (it: OrderItem) => {
    api
      .del(`/api/orders/${order.id}/items/${it.id}`)
      .then(() => {
        toastSaved(
          () =>
            api
              .post(`/api/orders/${order.id}/items`, {
                title: it.title ?? undefined,
                url: it.url ?? undefined,
                quantity: it.quantity,
                note: it.note ?? undefined,
              })
              .then(reload),
          "Позиция удалена",
        );
        reload();
      })
      .catch((err) => toastError(err.message));
  };

  return (
    <Section title={`Позиции (${order.order_items.length})`}>
      <div className="space-y-2">
        {order.order_items.length === 0 && (
          <p className="text-[12.5px] text-muted">
            Добавьте позиции или ссылки на товары — по ним работает поиск заказов.
          </p>
        )}
        {order.order_items.map((it) =>
          editingId === it.id ? (
            <ItemEditRow
              key={it.id}
              orderId={order.id}
              item={it}
              onDone={() => {
                setEditingId(null);
                reload();
              }}
              onCancel={() => setEditingId(null)}
            />
          ) : (
            <div key={it.id} className="flex flex-wrap items-center gap-x-2 gap-y-1 text-[13px]">
              <span className="font-medium">{it.title ?? itemDomain(it.url)}</span>
              {it.quantity > 1 && <Badge className="bg-zinc-500/10 text-muted">× {it.quantity}</Badge>}
              {it.url &&
                (safeHref(it.url) ? (
                  <a
                    href={it.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex max-w-56 items-center gap-0.5 font-mono text-[11.5px] text-accent hover:underline sm:max-w-80"
                  >
                    <span className="truncate">{it.url.replace(/^https?:\/\//, "")}</span>
                    <span aria-hidden>↗</span>
                  </a>
                ) : (
                  <span className="max-w-56 truncate font-mono text-[11.5px] text-muted sm:max-w-80">
                    {it.url}
                  </span>
                ))}
              {it.note && <span className="truncate text-[12px] text-muted">{it.note}</span>}
              <span className="ml-auto flex gap-1">
                <Button variant="ghost" className="h-7" onClick={() => setEditingId(it.id)}>
                  Изм.
                </Button>
                <Button variant="ghost" className="h-7" onClick={() => remove(it)}>
                  Удалить
                </Button>
              </span>
            </div>
          ),
        )}
        <form onSubmit={add} className="flex flex-wrap gap-2 pt-1">
          <Input
            className="sm:max-w-52"
            placeholder="Название"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
          />
          <Input
            className="font-mono sm:max-w-72"
            placeholder="https://…"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
          />
          <Input
            className="w-16 font-mono"
            inputMode="numeric"
            aria-label="Количество"
            value={qty}
            onChange={(e) => setQty(e.target.value)}
          />
          <Button type="submit" disabled={!title.trim() && !url.trim()}>
            Добавить позицию
          </Button>
        </form>
      </div>
    </Section>
  );
}

function TracksSection({ order }: { order: OrderDetail }) {
  const qc = useQueryClient();
  const [num, setNum] = useState("");
  const [carrier, setCarrier] = useState("");

  const reload = () => qc.invalidateQueries({ queryKey: ["order", order.id] });

  const add = (e: FormEvent) => {
    e.preventDefault();
    api
      .post<Track>(`/api/orders/${order.id}/tracks`, {
        tracking_number: num.trim(),
        carrier: carrier.trim() || undefined,
      })
      .then(() => {
        setNum("");
        setCarrier("");
        toastSaved(undefined, "Трек добавлен");
        reload();
        qc.invalidateQueries({ queryKey: ["tracks"] });
      })
      .catch((err) => toastError(err.message));
  };

  const unlink = (t: Track) => {
    api
      .post(`/api/tracks/${t.id}/assign`, { order_id: null })
      .then(() => {
        toastSaved(
          () => api.post(`/api/tracks/${t.id}/assign`, { order_id: order.id }).then(reload),
          "Трек отвязан",
        );
        reload();
      })
      .catch((err) => toastError(err.message));
  };

  return (
    <Section title={`Треки (${order.tracks.length})`}>
      <div className="space-y-2">
        {order.tracks.map((t) => (
          <div key={t.id} className="flex items-center gap-3 text-[13px]">
            <span className="font-mono">{t.tracking_number}</span>
            {t.carrier && <Badge className="bg-zinc-500/10 text-muted uppercase">{t.carrier}</Badge>}
            <Badge className="bg-zinc-500/10 text-muted">
              {t.source === "email" ? "из письма" : "вручную"}
            </Badge>
            <Button variant="ghost" className="ml-auto h-7" onClick={() => unlink(t)}>
              Отвязать
            </Button>
          </div>
        ))}
        <form onSubmit={add} className="flex flex-wrap gap-2 pt-1">
          <Input
            className="font-mono sm:max-w-72"
            placeholder="1Z999AA10123456784"
            value={num}
            onChange={(e) => setNum(e.target.value)}
          />
          <Input
            className="max-w-28"
            placeholder="UPS"
            value={carrier}
            onChange={(e) => setCarrier(e.target.value)}
          />
          <Button type="submit" disabled={!num.trim()}>
            Добавить трек
          </Button>
        </form>
      </div>
    </Section>
  );
}

function PaymentsSection({ order }: { order: OrderDetail }) {
  const qc = useQueryClient();
  const [amount, setAmount] = useState("");
  const [date, setDate] = useState(isoToday());
  const [comment, setComment] = useState("");

  const reload = () => qc.invalidateQueries({ queryKey: ["order", order.id] });

  const add = (e: FormEvent) => {
    e.preventDefault();
    api
      .post<Payment>(`/api/orders/${order.id}/payments`, {
        amount_usd: amount.trim(),
        paid_on: date,
        comment: comment.trim() || undefined,
      })
      .then(() => {
        setAmount("");
        setComment("");
        toastSaved(undefined, "Платёж записан");
        reload();
      })
      .catch((err) => toastError(err.message));
  };

  const remove = (p: Payment) => {
    api
      .del(`/api/payments/${p.id}`)
      .then(() => {
        toastSaved(
          () =>
            api
              .post(`/api/orders/${order.id}/payments`, {
                amount_usd: p.amount_usd,
                paid_on: p.paid_on,
                comment: p.comment ?? undefined,
              })
              .then(reload),
          "Платёж удалён",
        );
        reload();
      })
      .catch((err) => toastError(err.message));
  };

  return (
    <Section title={`Платежи (${order.payments.length}) · оплачено ${fmtMoney(order.finance.paid_usd)}`}>
      <div className="space-y-2">
        {order.payments.map((p) => (
          <div key={p.id} className="flex items-center gap-3 text-[13px]">
            <span className="w-24 text-muted">{fmtDate(p.paid_on)}</span>
            <span className="font-mono font-medium tnum">{fmtMoney(p.amount_usd)}</span>
            {p.comment && <span className="truncate text-muted">{p.comment}</span>}
            <Button variant="ghost" className="ml-auto h-7" onClick={() => remove(p)}>
              Удалить
            </Button>
          </div>
        ))}
        <form onSubmit={add} className="flex flex-wrap gap-2 pt-1">
          <Input
            className="max-w-28 font-mono"
            placeholder="0.00"
            inputMode="decimal"
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
          />
          <DatePicker
            className="w-44"
            value={date}
            onChange={(v) => setDate(v ?? isoToday())}
          />
          <Input
            className="sm:max-w-60"
            placeholder="Заметка"
            value={comment}
            onChange={(e) => setComment(e.target.value)}
          />
          <Button type="submit" disabled={!amount.trim()}>
            Записать платёж
          </Button>
        </form>
      </div>
    </Section>
  );
}
