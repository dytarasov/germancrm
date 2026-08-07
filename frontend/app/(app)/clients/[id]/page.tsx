"use client";

import { useParams } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "@/lib/api";
import type { ClientDetail } from "@/lib/api-types";
import { fmtMoney, safeHref } from "@/lib/format";
import { Card } from "@/components/ui";
import { InlineField } from "@/components/inline-field";
import { OrdersTable } from "@/components/orders-table";
import { toastError, toastSaved } from "@/components/toasts";

export default function ClientPage() {
  const { id } = useParams<{ id: string }>();
  const clientId = Number(id);
  const qc = useQueryClient();

  const { data, isLoading } = useQuery({
    queryKey: ["client", clientId],
    queryFn: () => api.get<ClientDetail>(`/api/clients/${clientId}`),
  });

  const patch = useMutation<unknown, ApiError, Record<string, unknown>>({
    mutationFn: (body) => api.patch(`/api/clients/${clientId}`, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["client", clientId] });
      qc.invalidateQueries({ queryKey: ["clients"] });
    },
    onError: (e) => toastError(e.message),
  });

  if (isLoading || !data)
    return <p className="py-16 text-center text-[13px] text-muted">Загрузка…</p>;

  const c = data.client;
  const save = (field: string, v: string | null, old: string | null) =>
    patch.mutate(
      { [field]: v },
      { onSuccess: () => toastSaved(() => patch.mutate({ [field]: old })) },
    );

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-[17px] font-semibold tracking-tight">{c.name}</h1>
        {safeHref(c.telegram_url) && (
          <a
            href={c.telegram_url!}
            target="_blank"
            rel="noopener noreferrer"
            className="text-[13px] text-accent hover:underline"
          >
            Написать в Telegram →
          </a>
        )}
      </div>

      <div className="grid grid-cols-1 gap-3 lg:grid-cols-3">
        <Card className="grid grid-cols-1 gap-x-4 gap-y-3 p-4 sm:grid-cols-2 lg:col-span-2">
          <InlineField label="Имя" value={c.name} onSave={(v) => v && save("name", v, c.name)} />
          <InlineField
            label="Telegram"
            value={c.telegram_url}
            placeholder="https://t.me/…"
            onSave={(v) => save("telegram_url", v, c.telegram_url)}
          />
          <InlineField
            label="Контакты"
            value={c.contacts}
            onSave={(v) => save("contacts", v, c.contacts)}
          />
          <InlineField
            label="Заметка"
            value={c.note}
            onSave={(v) => save("note", v, c.note)}
          />
        </Card>
        <Card className="space-y-2.5 p-4">
          <div className="flex items-baseline justify-between">
            <span className="text-[12.5px] text-muted">Долг</span>
            <span className="font-mono text-[15px] font-semibold tnum">{fmtMoney(data.debt_usd)}</span>
          </div>
          <div className="flex items-baseline justify-between">
            <span className="text-[12.5px] text-muted">Заработано за всё время</span>
            <span className="font-mono text-[15px] font-semibold text-green-600 tnum dark:text-green-400">
              {fmtMoney(data.earned_usd)}
            </span>
          </div>
        </Card>
      </div>

      <Card>
        {data.orders.length === 0 ? (
          <p className="py-8 text-center text-[13px] text-muted">Заказов пока нет</p>
        ) : (
          <OrdersTable orders={data.orders} />
        )}
      </Card>
    </div>
  );
}
