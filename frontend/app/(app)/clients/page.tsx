"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { keepPreviousData, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { ClientListItem } from "@/lib/api-types";
import { fmtMoney, safeHref } from "@/lib/format";
import { useDebounced } from "@/lib/use-debounced";
import { Button, Card, EmptyState, Field, Input, Modal } from "@/components/ui";
import { toastError } from "@/components/toasts";

function NewClientModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const router = useRouter();
  const qc = useQueryClient();
  const [name, setName] = useState("");
  const [contacts, setContacts] = useState("");
  const [telegram, setTelegram] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    try {
      const c = await api.post<ClientListItem>("/api/clients", {
        name: name.trim(),
        contacts: contacts.trim() || undefined,
        telegram_url: telegram.trim() || undefined,
      });
      qc.invalidateQueries({ queryKey: ["clients"] });
      router.push(`/clients/${c.id}`);
    } catch (err) {
      toastError(err instanceof Error ? err.message : "Не удалось создать клиента");
      setBusy(false);
    }
  };

  return (
    <Modal open={open} onClose={onClose} title="Новый клиент">
      <form onSubmit={submit} className="space-y-3">
        <Field label="Имя">
          <Input autoFocus value={name} onChange={(e) => setName(e.target.value)} />
        </Field>
        <Field label="Telegram (ссылка или @ник)">
          <Input
            placeholder="https://t.me/…"
            value={telegram}
            onChange={(e) => setTelegram(e.target.value)}
          />
        </Field>
        <Field label="Контакты">
          <Input
            placeholder="телефон, почта…"
            value={contacts}
            onChange={(e) => setContacts(e.target.value)}
          />
        </Field>
        <div className="flex justify-end gap-2 pt-1">
          <Button type="button" variant="ghost" onClick={onClose}>
            Отмена
          </Button>
          <Button type="submit" variant="primary" disabled={!name.trim() || busy}>
            Создать
          </Button>
        </div>
      </form>
    </Modal>
  );
}

export default function ClientsPage() {
  const router = useRouter();
  const [search, setSearch] = useState("");
  const [modal, setModal] = useState(false);

  const debouncedSearch = useDebounced(search.trim());
  const { data: clients, isLoading } = useQuery({
    queryKey: ["clients", debouncedSearch],
    queryFn: () => api.get<ClientListItem[]>("/api/clients", { search: debouncedSearch || undefined }),
    placeholderData: keepPreviousData,
  });

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-[17px] font-semibold tracking-tight">Клиенты</h1>
        <Button variant="primary" onClick={() => setModal(true)}>
          Новый клиент
        </Button>
      </div>

      <Input
        className="max-w-72"
        placeholder="Поиск по имени…"
        value={search}
        onChange={(e) => setSearch(e.target.value)}
      />

      <Card>
        {isLoading ? (
          <p className="py-12 text-center text-[13px] text-muted">Загрузка…</p>
        ) : (clients ?? []).length === 0 ? (
          <EmptyState title="Клиентов пока нет" hint="Клиент появится вместе с первым заказом." />
        ) : (
          <div className="overflow-x-auto">
          <table className="w-full min-w-[560px]">
            <thead>
              <tr className="border-b border-line text-left text-[11.5px] tracking-wide text-muted uppercase">
                <th className="px-3 py-2 font-medium">Имя</th>
                <th className="px-3 py-2 font-medium">Telegram</th>
                <th className="px-3 py-2 text-right font-medium">Активных заказов</th>
                <th className="px-3 py-2 text-right font-medium">Долг</th>
              </tr>
            </thead>
            <tbody>
              {(clients ?? []).map((c) => (
                <tr
                  key={c.id}
                  tabIndex={0}
                  role="link"
                  aria-label={`Клиент ${c.name}`}
                  onClick={() => router.push(`/clients/${c.id}`)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      router.push(`/clients/${c.id}`);
                    }
                  }}
                  className="cursor-pointer border-b border-line/60 last:border-0 hover:bg-surface2/60"
                >
                  <td className="px-3 py-2.5 text-[13px] font-medium">{c.name}</td>
                  <td className="px-3 py-2.5">
                    {c.telegram_url ? (
                      safeHref(c.telegram_url) ? (
                        <a
                          href={c.telegram_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          onClick={(e) => e.stopPropagation()}
                          className="text-[12.5px] text-accent hover:underline"
                        >
                          {c.telegram_url.replace(/^https?:\/\/(t\.me\/)?/, "@").replace(/^@@/, "@")}
                        </a>
                      ) : (
                        <span className="text-[12.5px] text-muted">{c.telegram_url}</span>
                      )
                    ) : (
                      <span className="text-[12.5px] text-muted">—</span>
                    )}
                  </td>
                  <td className="px-3 py-2.5 text-right text-[13px] tnum">{c.active_orders}</td>
                  <td className="px-3 py-2.5 text-right font-mono text-[13px] tnum">
                    {fmtMoney(c.debt_usd)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          </div>
        )}
      </Card>

      <NewClientModal open={modal} onClose={() => setModal(false)} />
    </div>
  );
}
