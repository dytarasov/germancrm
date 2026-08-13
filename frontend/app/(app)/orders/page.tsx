"use client";

import { FormEvent, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { keepPreviousData, useQuery, useQueryClient } from "@tanstack/react-query";
import { useDebounced } from "@/lib/use-debounced";
import { api } from "@/lib/api";
import type { ClientListItem, OrderDetail, OrderListItem, OrderStatus, Settings } from "@/lib/api-types";
import { STATUS_LABEL } from "@/lib/status";
import { fmtMoney } from "@/lib/format";
import { Badge, Button, Card, EmptyState, Field, Input, Modal, Seg, Textarea } from "@/components/ui";
import { SelectBox } from "@/components/select-box";
import { Combobox } from "@/components/combobox";
import { DatePicker } from "@/components/date-picker";
import { OrderCard, OrderRow, OrdersTableHead } from "@/components/orders-table";
import { toastError } from "@/components/toasts";

type SegVal = "active" | "closed" | "all";

// столько же, сколько MAX_SUBORDERS на бэке (OrderCreate.suborders max_length)
const MAX_SUBORDERS = 20;

const ALL_STATUSES: OrderStatus[] = [
  "purchased",
  "shipped",
  "at_warehouse",
  "in_flight",
  "delivered",
  "closed",
  "cancelled",
  "refunded",
];

function NewOrderModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const router = useRouter();
  const qc = useQueryClient();
  const { data: clients } = useQuery({
    queryKey: ["clients", ""],
    queryFn: () => api.get<ClientListItem[]>("/api/clients"),
    enabled: open,
  });
  const { data: settings } = useQuery({
    queryKey: ["settings"],
    queryFn: () => api.get<Settings>("/api/settings"),
    enabled: open,
  });

  const [clientId, setClientId] = useState<string>("");
  const [newClient, setNewClient] = useState(false);
  const [clientName, setClientName] = useState("");
  // Защита от дублей: при ретрае после ошибки не создаём клиента второй раз.
  const [createdClientId, setCreatedClientId] = useState<number | null>(null);
  const [store, setStore] = useState("");
  // подзаказы: номера заказов магазина + справочные суммы (корзина может разбиться)
  const [subs, setSubs] = useState([{ number: "", amount: "" }]);
  const [items, setItems] = useState("");
  const [links, setLinks] = useState("");
  const [price, setPrice] = useState("");
  const [commission, setCommission] = useState("");
  const [estWeight, setEstWeight] = useState("");
  const [promised, setPromised] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    try {
      let cid = Number(clientId);
      if (newClient) {
        if (createdClientId !== null) {
          cid = createdClientId;
        } else {
          const created = await api.post<ClientListItem>("/api/clients", {
            name: clientName.trim(),
          });
          setCreatedClientId(created.id);
          cid = created.id;
        }
      }
      const linkList = links.split(/\s+/).map((s) => s.trim()).filter(Boolean);
      const subList = subs
        .map((s) => ({ number: s.number.trim(), amount: s.amount.trim() }))
        .filter((s) => s.number || s.amount);
      const order = await api.post<OrderDetail>("/api/orders", {
        client_id: cid,
        store: store.trim(),
        suborders:
          subList.length > 0
            ? subList.map((s) => ({
                store_order_number: s.number || null,
                amount_usd: s.amount ? s.amount.replace(",", ".") : null,
              }))
            : undefined,
        items: items.trim(),
        purchase_price_usd: price.trim(),
        commission_usd: commission.trim() || undefined,
        est_weight_kg: estWeight.trim().replace(",", ".") || undefined,
        promised_date: promised || null,
        links: linkList.length > 0 ? linkList : undefined,
      });
      qc.invalidateQueries({ queryKey: ["orders"] });
      qc.invalidateQueries({ queryKey: ["clients"] });
      router.push(`/orders/${order.id}`);
    } catch (err) {
      toastError(err instanceof Error ? err.message : "Не удалось создать заказ");
      setBusy(false);
    }
  };

  const valid =
    (newClient ? clientName.trim() : clientId) && store.trim() && items.trim() && price.trim();

  // Прогноз комиссии от предполагаемого веса — ориентир, в БД не пишется.
  const tariff = settings?.commission_per_kg_usd ?? 50;
  const estW = parseFloat(estWeight.replace(",", "."));
  const estCommissionHint =
    commission.trim() === "" && Number.isFinite(estW) && estW > 0
      ? `Ориентир: ${estW} кг × $${tariff}/кг ≈ $${(estW * tariff).toFixed(2)}. Это прогноз — закрыть заказ можно будет только с настоящей комиссией (появится от фактического веса или руками).`
      : null;

  return (
    <Modal open={open} onClose={onClose} title="Новый заказ">
      <form onSubmit={submit} className="space-y-3">
        <Field label="Клиент">
          {newClient ? (
            <div className="flex gap-2">
              <Input
                autoFocus
                placeholder="Имя нового клиента"
                value={clientName}
                onChange={(e) => {
                  setClientName(e.target.value);
                  setCreatedClientId(null);
                }}
              />
              <Button type="button" variant="ghost" onClick={() => setNewClient(false)}>
                Выбрать
              </Button>
            </div>
          ) : (
            <div className="flex gap-2">
              <Combobox
                className="min-w-0 flex-1"
                value={clientId}
                onChange={setClientId}
                placeholder="— выберите —"
                searchPlaceholder="Имя клиента…"
                options={(clients ?? []).map((c) => ({ value: String(c.id), label: c.name }))}
              />
              <Button type="button" variant="ghost" onClick={() => setNewClient(true)}>
                + Новый
              </Button>
            </div>
          )}
        </Field>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <Field label="Магазин">
            <Input placeholder="Amazon" value={store} onChange={(e) => setStore(e.target.value)} />
          </Field>
          <Field label="Цена закупки, $">
            <Input
              placeholder="0.00"
              inputMode="decimal"
              className="font-mono"
              value={price}
              onChange={(e) => setPrice(e.target.value)}
            />
          </Field>
        </div>
        <Field label="Номера заказов магазина (можно позже; несколько, если корзина разбилась)">
          <div className="space-y-2">
            {subs.map((s, i) => (
              <div key={i} className="flex gap-2">
                <Input
                  placeholder="111-2345678-1234567"
                  className="min-w-0 flex-1 font-mono"
                  value={s.number}
                  onChange={(e) =>
                    setSubs(subs.map((x, j) => (j === i ? { ...x, number: e.target.value } : x)))
                  }
                />
                <Input
                  placeholder="сумма $"
                  inputMode="decimal"
                  className="w-24 font-mono"
                  value={s.amount}
                  onChange={(e) =>
                    setSubs(subs.map((x, j) => (j === i ? { ...x, amount: e.target.value } : x)))
                  }
                />
                {subs.length > 1 && (
                  <Button
                    type="button"
                    variant="ghost"
                    aria-label="Убрать подзаказ"
                    onClick={() => setSubs(subs.filter((_, j) => j !== i))}
                  >
                    ×
                  </Button>
                )}
              </div>
            ))}
            <Button
              type="button"
              variant="ghost"
              disabled={subs.length >= MAX_SUBORDERS}
              onClick={() => setSubs([...subs, { number: "", amount: "" }])}
            >
              + ещё номер (подзаказ)
            </Button>
            {subs.length >= MAX_SUBORDERS && (
              <p className="text-[12px] text-muted">
                Максимум {MAX_SUBORDERS} подзаказов в одном заказе.
              </p>
            )}
          </div>
        </Field>
        <Field label="Товар">
          <Input
            placeholder="iPhone 17 Pro 256GB"
            value={items}
            onChange={(e) => setItems(e.target.value)}
          />
        </Field>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <Field label="Комиссия, $ (можно позже)">
            <Input
              placeholder="0.00"
              inputMode="decimal"
              className="font-mono"
              value={commission}
              onChange={(e) => setCommission(e.target.value)}
            />
          </Field>
          <Field label="Предполагаемый вес, кг">
            <Input
              placeholder="0.0"
              inputMode="decimal"
              className="font-mono"
              value={estWeight}
              onChange={(e) => setEstWeight(e.target.value)}
            />
          </Field>
        </div>
        {estCommissionHint && (
          <p className="text-[12px] text-muted">{estCommissionHint}</p>
        )}
        <Field label="Ссылки на товар (по одной на строку, необязательно)">
          <Textarea
            rows={3}
            className="font-mono"
            placeholder={"https://amazon.com/…\nhttps://ebay.com/…"}
            value={links}
            onChange={(e) => setLinks(e.target.value)}
          />
        </Field>
        <Field label="Обещанная дата (можно позже)">
          <DatePicker
            className="w-full"
            clearable
            value={promised || null}
            onChange={(v) => setPromised(v ?? "")}
          />
        </Field>
        <p className="text-[12px] text-muted">
          Фактический вес и треки добавите в карточке, когда появятся.
        </p>
        <div className="flex justify-end gap-2 pt-1">
          <Button type="button" variant="ghost" onClick={onClose}>
            Отмена
          </Button>
          <Button type="submit" variant="primary" disabled={!valid || busy}>
            {busy ? "Создаю…" : "Создать заказ"}
          </Button>
        </div>
      </form>
    </Modal>
  );
}

export default function OrdersPage() {
  const [seg, setSeg] = useState<SegVal>("active");
  const [status, setStatus] = useState("");
  const [clientId, setClientId] = useState("");
  const [search, setSearch] = useState("");
  const [modal, setModal] = useState(false);

  const debouncedSearch = useDebounced(search.trim());
  const params: Record<string, string | boolean | undefined> = {
    search: debouncedSearch || undefined,
    status: status || undefined,
    client_id: clientId || undefined,
  };
  if (seg === "active") params.active = true;
  if (seg === "closed") params.active = false;

  const { data: orders, isLoading } = useQuery({
    queryKey: ["orders", params],
    queryFn: () => api.get<OrderListItem[]>("/api/orders", params),
    placeholderData: keepPreviousData,
  });
  const { data: clients } = useQuery({
    queryKey: ["clients", ""],
    queryFn: () => api.get<ClientListItem[]>("/api/clients"),
  });

  const groups = useMemo(() => {
    const map = new Map<number, { name: string; orders: OrderListItem[] }>();
    for (const o of orders ?? []) {
      const g = map.get(o.client_id) ?? { name: o.client_name, orders: [] };
      g.orders.push(o);
      map.set(o.client_id, g);
    }
    return [...map.entries()].sort((a, b) => a[1].name.localeCompare(b[1].name, "ru"));
  }, [orders]);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-[17px] font-semibold tracking-tight">Заказы</h1>
        <Button variant="primary" onClick={() => setModal(true)}>
          Новый заказ
        </Button>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <Seg
          value={seg}
          onChange={setSeg}
          options={[
            { value: "active", label: "Активные" },
            { value: "closed", label: "Закрытые" },
            { value: "all", label: "Все" },
          ]}
        />
        <SelectBox
          value={status}
          onChange={setStatus}
          placeholder="Статус"
          options={[
            { value: "", label: "Любой статус" },
            ...ALL_STATUSES.map((s) => ({ value: s, label: STATUS_LABEL[s] })),
          ]}
        />
        <SelectBox
          value={clientId}
          onChange={setClientId}
          placeholder="Клиент"
          options={[
            { value: "", label: "Все клиенты" },
            ...(clients ?? []).map((c) => ({ value: String(c.id), label: c.name })),
          ]}
        />
        <Input
          className="w-full sm:max-w-60"
          placeholder="Поиск: имя, номер, трек…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
      </div>

      <Card>
        {isLoading ? (
          <p className="py-12 text-center text-[13px] text-muted">Загрузка…</p>
        ) : (orders ?? []).length === 0 ? (
          <EmptyState
            title="Заказов не найдено"
            hint="Создайте первый заказ — кнопка «Новый заказ» справа сверху."
          />
        ) : (
          <>
            {/* Таблица (sm+), при нехватке ширины скроллится внутри карточки */}
            <div className="hidden overflow-x-auto sm:block">
              <table className="w-full min-w-[720px]">
                <OrdersTableHead showClient />
                <tbody>
                  {groups.map(([cid, g]) => {
                    const debt = g.orders.reduce(
                      (s, o) => s + (o.due_usd !== null ? parseFloat(o.due_usd) : 0),
                      0,
                    );
                    const noCom = g.orders.filter((o) => o.commission_usd === null).length;
                    return [
                      <tr key={`g${cid}`} className="border-b border-line bg-surface2/70">
                        <td colSpan={6} className="border-l-2 border-l-accent px-3 py-1.5">
                          <Link
                            href={`/clients/${cid}`}
                            className="text-[12.5px] font-semibold text-accent hover:underline"
                          >
                            {g.name}
                          </Link>
                          <span className="ml-2 text-[12px] text-muted">
                            {g.orders.length} зак. · остаток {fmtMoney(debt)}
                          </span>
                          {noCom > 0 && (
                            <Badge className="ml-2 bg-amber-500/15 text-amber-700 dark:text-amber-400">
                              +{noCom} без комиссии
                            </Badge>
                          )}
                        </td>
                      </tr>,
                      ...g.orders.map((o) => <OrderRow key={o.id} order={o} showClient />),
                    ];
                  })}
                </tbody>
              </table>
            </div>
            {/* Карточки (<sm), группировка по клиентам сохраняется */}
            <div className="sm:hidden">
              {groups.map(([cid, g]) => {
                const debt = g.orders.reduce(
                  (s, o) => s + (o.due_usd !== null ? parseFloat(o.due_usd) : 0),
                  0,
                );
                const noCom = g.orders.filter((o) => o.commission_usd === null).length;
                return (
                  <div key={cid}>
                    <div className="border-y border-line border-l-2 border-l-accent bg-surface2/70 px-3 py-1.5 first:border-t-0">
                      <Link
                        href={`/clients/${cid}`}
                        className="text-[12.5px] font-semibold text-accent hover:underline"
                      >
                        {g.name}
                      </Link>
                      <span className="ml-2 text-[12px] text-muted">
                        {g.orders.length} зак. · {fmtMoney(debt)}
                      </span>
                      {noCom > 0 && (
                        <Badge className="ml-2 bg-amber-500/15 text-amber-700 dark:text-amber-400">
                          +{noCom} без комиссии
                        </Badge>
                      )}
                    </div>
                    <ul className="divide-y divide-line/60">
                      {g.orders.map((o) => (
                        <OrderCard key={o.id} order={o} />
                      ))}
                    </ul>
                  </div>
                );
              })}
            </div>
          </>
        )}
      </Card>

      <NewOrderModal open={modal} onClose={() => setModal(false)} />
    </div>
  );
}
