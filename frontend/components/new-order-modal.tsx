"use client";

import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { ClientListItem, OrderDetail, Settings } from "@/lib/api-types";
import { fmtMoney } from "@/lib/format";
import { Button, Field, Input, Modal, Textarea } from "./ui";
import { Combobox } from "./combobox";
import { DatePicker } from "./date-picker";
import { toastError } from "./toasts";

// столько же, сколько MAX_SUBORDERS на бэке (OrderCreate.suborders max_length)
const MAX_SUBORDERS = 20;

export function parseMoney(v: string | null | undefined): number {
  return parseFloat((v ?? "").replace(",", ".").replace(/\s/g, ""));
}

/** Подсказка под «Ценой закупки»: закупка + наценка из настроек, чтобы не лезть в калькулятор. */
export function markupHint(
  price: string | null | undefined,
  markupPct: number,
): string | undefined {
  const p = parseMoney(price);
  if (!Number.isFinite(p) || p <= 0) return undefined;
  return `Предполагаемая цена с комиссией (+${markupPct}%): ${fmtMoney(p * (1 + markupPct / 100))}`;
}

export function NewOrderModal({
  open,
  onClose,
  defaultClientId,
}: {
  open: boolean;
  onClose: () => void;
  /** клиент, из карточки которого открыли форму */
  defaultClientId?: number;
}) {
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
  const [total, setTotal] = useState(""); // полная стоимость = закупка + комиссия
  const [commission, setCommission] = useState("");
  const [estWeight, setEstWeight] = useState("");
  const [promised, setPromised] = useState("");
  const [busy, setBusy] = useState(false);

  // Открыли из карточки клиента — клиент уже выбран.
  useEffect(() => {
    if (open && defaultClientId !== undefined) {
      setClientId(String(defaultClientId));
      setNewClient(false);
    }
  }, [open, defaultClientId]);

  // Полная стоимость + закупка → финальная комиссия (ручная комиссия главнее).
  const priceNum = parseFloat(price.replace(",", "."));
  const totalNum = parseFloat(total.replace(",", "."));
  const totalCommission =
    commission.trim() === "" &&
    Number.isFinite(totalNum) &&
    Number.isFinite(priceNum) &&
    totalNum >= priceNum
      ? (totalNum - priceNum).toFixed(2)
      : null;
  const totalInvalid =
    total.trim() !== "" &&
    Number.isFinite(totalNum) &&
    Number.isFinite(priceNum) &&
    totalNum < priceNum;

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
      const linkList = links
        .split(/\s+/)
        .map((s) => s.trim())
        .filter(Boolean);
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
        commission_usd: commission.trim() || totalCommission || undefined,
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
    (newClient ? clientName.trim() : clientId) &&
    store.trim() &&
    items.trim() &&
    price.trim() &&
    !totalInvalid;

  const priceHint = markupHint(price, settings?.markup_pct ?? 25);
  // Справочная автосумма подзаказов — сверить с ценой закупки.
  const subAmounts = subs.map((s) => parseMoney(s.amount)).filter(Number.isFinite);
  const subSum = subAmounts.length >= 2 ? subAmounts.reduce((a, b) => a + b, 0) : null;

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
                options={(clients ?? []).map((c) => ({
                  value: String(c.id),
                  label: c.name,
                }))}
              />
              <Button type="button" variant="ghost" onClick={() => setNewClient(true)}>
                + Новый
              </Button>
            </div>
          )}
        </Field>
        <Field label="Магазин">
          <Input placeholder="Amazon" value={store} onChange={(e) => setStore(e.target.value)} />
        </Field>
        <Field label="Номера заказов магазина (можно позже; несколько, если корзина разбилась)">
          <div className="space-y-2">
            {subs.map((s, i) => (
              <div key={i} className="flex flex-wrap gap-2">
                {/* на телефоне длинный моноширинный номер занимает всю строку,
                    сумма и «×» уходят на вторую; на sm+ всё в одну строку */}
                <Input
                  placeholder="111-2345678-1234567"
                  className="w-full font-mono sm:min-w-0 sm:flex-1"
                  value={s.number}
                  onChange={(e) =>
                    setSubs(subs.map((x, j) => (j === i ? { ...x, number: e.target.value } : x)))
                  }
                />
                <Input
                  placeholder="сумма $"
                  inputMode="decimal"
                  className="min-w-0 flex-1 font-mono sm:w-24 sm:flex-none"
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
            {subSum !== null && (
              <p className="text-[12px] text-muted">
                Сумма подзаказов: <span className="font-mono tnum">{fmtMoney(subSum)}</span>
                {price.trim() === "" && (
                  <button
                    type="button"
                    className="ml-2 text-accent hover:underline"
                    onClick={() => setPrice(subSum.toFixed(2))}
                  >
                    взять как цену закупки
                  </button>
                )}
              </p>
            )}
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
        {/* Деньги — одной сеткой 2×2 */}
        <div className="grid grid-cols-2 gap-3 rounded-md border border-line p-3">
          <Field label="Цена закупки, $">
            <Input
              placeholder="0.00"
              inputMode="decimal"
              className="font-mono"
              value={price}
              onChange={(e) => setPrice(e.target.value)}
            />
          </Field>
          <Field label="Полная стоимость, $">
            <Input
              placeholder="закупка + комиссия"
              inputMode="decimal"
              className="font-mono"
              value={total}
              onChange={(e) => setTotal(e.target.value)}
            />
          </Field>
          {priceHint && <p className="col-span-2 -mt-1.5 text-[12px] text-accent">{priceHint}</p>}
          <Field label="Комиссия, $ (можно позже)">
            <Input
              placeholder={totalCommission ?? "0.00"}
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
          {totalInvalid && (
            <p className="col-span-2 text-[12px] text-red-600 dark:text-red-400">
              Полная стоимость меньше закупки — комиссия вышла бы отрицательной.
            </p>
          )}
          {totalCommission && (
            <p className="col-span-2 text-[12px] text-muted">
              Комиссия ${totalCommission} = полная стоимость − закупка. Это финальная комиссия — с
              ней заказ можно закрывать.
            </p>
          )}
          {estCommissionHint && !totalCommission && (
            <p className="col-span-2 text-[12px] text-muted">{estCommissionHint}</p>
          )}
        </div>
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
