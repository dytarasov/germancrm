"use client";

import { FormEvent, useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { Flight } from "@/lib/api-types";
import { isoToday } from "@/lib/format";
import { Button, Field, Input, Modal } from "./ui";
import { DatePicker } from "./date-picker";
import { toastError, toastSaved } from "./toasts";

/** Правка даты/стоимости/описания рейса — со списка рейсов и со страницы рейса. */
export function EditFlightModal({ flight, onClose }: { flight: Flight | null; onClose: () => void }) {
  const qc = useQueryClient();
  const [date, setDate] = useState(isoToday());
  const [cost, setCost] = useState("");
  const [desc, setDesc] = useState("");
  const [busy, setBusy] = useState(false);

  // При каждом открытии заполняем форму текущими значениями рейса.
  useEffect(() => {
    if (flight) {
      setDate(flight.departed_on);
      setCost(flight.cost_usd);
      setDesc(flight.description ?? "");
    }
  }, [flight]);

  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (!flight) return;
    setBusy(true);
    api
      .patch<Flight>(`/api/flights/${flight.id}`, {
        departed_on: date,
        cost_usd: cost.trim(),
        description: desc.trim() || null,
      })
      .then(() => {
        toastSaved(undefined, "Рейс обновлён");
        qc.invalidateQueries({ queryKey: ["flights"] });
        qc.invalidateQueries({ queryKey: ["flight", flight.id] });
        qc.invalidateQueries({ queryKey: ["dashboard"] });
        qc.invalidateQueries({ queryKey: ["money"] });
        onClose();
      })
      .catch((err) => toastError(err.message))
      .finally(() => setBusy(false));
  };

  return (
    <Modal open={flight !== null} onClose={onClose} title="Изменить рейс">
      <form onSubmit={submit} className="space-y-3">
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <Field label="Дата вылета">
            <DatePicker
              className="w-full"
              value={date}
              onChange={(v) => setDate(v ?? isoToday())}
            />
          </Field>
          <Field label="Стоимость, $">
            <Input
              className="font-mono"
              placeholder="0.00"
              inputMode="decimal"
              value={cost}
              onChange={(e) => setCost(e.target.value)}
            />
          </Field>
        </div>
        <Field label="Описание">
          <Input
            placeholder="партия №, вес, примечание…"
            value={desc}
            onChange={(e) => setDesc(e.target.value)}
          />
        </Field>
        <div className="flex justify-end gap-2 pt-1">
          <Button type="button" variant="ghost" onClick={onClose}>
            Отмена
          </Button>
          <Button type="submit" variant="primary" disabled={!cost.trim() || busy}>
            {busy ? "Сохраняю…" : "Сохранить"}
          </Button>
        </div>
      </form>
    </Modal>
  );
}
