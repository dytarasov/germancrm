"use client";

import { KeyboardEvent, useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "@/lib/api";
import type { Settings } from "@/lib/api-types";
import { Badge, Button, Card, Input, Section, Spinner } from "@/components/ui";
import { toastError, toastSaved } from "@/components/toasts";

function Chips({
  values,
  onChange,
  placeholder,
}: {
  values: string[];
  onChange: (v: string[]) => void;
  placeholder: string;
}) {
  const [draft, setDraft] = useState("");

  const add = () => {
    const v = draft.trim().toLowerCase();
    if (!v || values.includes(v)) {
      setDraft("");
      return;
    }
    onChange([...values, v]);
    setDraft("");
  };

  const onKey = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter" || e.key === ",") {
      e.preventDefault();
      add();
    }
  };

  return (
    <div className="flex flex-wrap items-center gap-1.5 rounded-md border border-line bg-surface p-1.5">
      {values.map((v) => (
        <Badge key={v} className="bg-surface2 font-mono text-[11.5px] text-ink">
          {v}
          <button
            aria-label={`Убрать ${v}`}
            className="ml-0.5 text-muted hover:text-ink"
            onClick={() => onChange(values.filter((x) => x !== v))}
          >
            ×
          </button>
        </Badge>
      ))}
      <input
        className="h-6 min-w-40 flex-1 bg-transparent px-1 text-[12.5px] outline-none placeholder:text-muted/60"
        placeholder={placeholder}
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={onKey}
        onBlur={add}
      />
    </div>
  );
}

export default function SettingsPage() {
  const qc = useQueryClient();
  const { data: settings } = useQuery({
    queryKey: ["settings"],
    queryFn: () => api.get<Settings>("/api/settings"),
  });

  const [model, setModel] = useState("");
  const [interval, setIntervalSec] = useState("");
  const [testResult, setTestResult] = useState<{ ok: boolean; message: string } | null>(null);
  const [testing, setTesting] = useState(false);

  useEffect(() => {
    if (settings) {
      setModel(settings.llm_model);
      setIntervalSec(String(settings.poll_interval_sec));
    }
  }, [settings]);

  const patch = useMutation<Settings, ApiError, Partial<Settings>>({
    mutationFn: (body) => api.patch<Settings>("/api/settings", body),
    onSuccess: (d) => {
      qc.setQueryData(["settings"], d);
      toastSaved();
    },
    onError: (e) => toastError(e.message),
  });

  const connectGmail = () => {
    api
      .get<{ url: string }>("/api/mail/oauth/url")
      .then((r) => {
        window.location.href = r.url;
      })
      .catch((e) => toastError(e.message));
  };

  const testLlm = () => {
    setTesting(true);
    setTestResult(null);
    api
      .post<{ ok: boolean; model: string; message: string }>("/api/settings/llm-test")
      .then((r) => setTestResult({ ok: r.ok, message: `${r.model}: ${r.message}` }))
      .catch((e) => setTestResult({ ok: false, message: e.message }))
      .finally(() => setTesting(false));
  };

  if (!settings) return <p className="py-16 text-center text-[13px] text-muted">Загрузка…</p>;

  return (
    <div className="mx-auto max-w-3xl space-y-4">
      <h1 className="text-[17px] font-semibold tracking-tight">Настройки</h1>

      <Section title="Комиссия">
        <label className="flex flex-wrap items-center gap-2 text-[13px]">
          Тариф
          <Input
            className="w-24 font-mono"
            inputMode="decimal"
            defaultValue={settings.commission_per_kg_usd}
            onBlur={(e) => {
              const n = parseFloat(e.target.value.replace(",", "."));
              if (!Number.isFinite(n) || n < 0) {
                toastError("Тариф — неотрицательное число");
                e.target.value = String(settings.commission_per_kg_usd);
                return;
              }
              if (n !== settings.commission_per_kg_usd)
                patch.mutate({ commission_per_kg_usd: n });
            }}
          />
          $/кг
          <span className="text-[12px] text-muted">
            от него считаются ориентир по предполагаемому весу и автокомиссия от фактического
          </span>
        </label>
      </Section>

      <Section title="Gmail">
        {settings.gmail.connected ? (
          <div className="flex flex-wrap items-center gap-3 text-[13px]">
            <span className="inline-block size-1.5 rounded-full bg-green-500" />
            Подключён: <b>{settings.gmail.email}</b>
            {settings.gmail.needs_reauth && (
              <Badge className="bg-red-500/12 text-red-700 dark:text-red-400">
                требуется повторная авторизация
              </Badge>
            )}
            <Button className="ml-auto" onClick={connectGmail}>
              {settings.gmail.needs_reauth ? "Авторизовать заново" : "Переподключить"}
            </Button>
          </div>
        ) : (
          <div className="flex flex-wrap items-center justify-between gap-3">
            <p className="text-[13px] text-muted">
              Подключите рабочую почту — приложение будет читать письма магазинов и двигать
              статусы. Нужны GOOGLE_OAUTH_CLIENT_ID/SECRET в .env.
            </p>
            <Button variant="primary" onClick={connectGmail}>
              Подключить Gmail
            </Button>
          </div>
        )}
      </Section>

      <Section title="LLM (OpenRouter)">
        <div className="space-y-3">
          <div className="flex flex-wrap items-end gap-2">
            <div className="min-w-52 flex-1">
              <div className="mb-1 text-[12px] font-medium text-muted">
                Модель (слаг OpenRouter)
              </div>
              <Input
                className="font-mono"
                placeholder="anthropic/claude-haiku-4.5"
                value={model}
                onChange={(e) => setModel(e.target.value)}
                onBlur={() => {
                  if (model.trim() && model.trim() !== settings.llm_model)
                    patch.mutate({ llm_model: model.trim() });
                }}
              />
            </div>
            <Button onClick={testLlm} disabled={testing}>
              {testing ? <Spinner /> : "Проверить"}
            </Button>
            <label className="flex h-8 items-center gap-1.5 px-1 text-[13px]">
              <input
                type="checkbox"
                checked={settings.llm_enabled}
                onChange={(e) => patch.mutate({ llm_enabled: e.target.checked })}
              />
              включён
            </label>
          </div>
          {testResult && (
            <p
              className={
                "text-[12.5px] " +
                (testResult.ok
                  ? "text-green-600 dark:text-green-400"
                  : "text-red-600 dark:text-red-400")
              }
            >
              {testResult.message}
            </p>
          )}
          <label className="flex flex-wrap items-center gap-2 text-[13px]">
            Порог уверенности LLM (0–1)
            <Input
              className="w-24 font-mono"
              inputMode="decimal"
              defaultValue={settings.llm_auto_min_confidence}
              onBlur={(e) => {
                const n = parseFloat(e.target.value.replace(",", "."));
                if (!Number.isFinite(n) || n < 0 || n > 1) {
                  toastError("Порог уверенности — число от 0 до 1");
                  e.target.value = String(settings.llm_auto_min_confidence);
                  return;
                }
                if (n !== settings.llm_auto_min_confidence)
                  patch.mutate({ llm_auto_min_confidence: n });
              }}
            />
            <span className="text-[12px] text-muted">
              ниже порога — событие не применяется автоматически
            </span>
          </label>
          <p className="text-[12px] text-muted">
            Без ключа OPENROUTER_API_KEY или при выключенном LLM письма копятся в очереди ручного
            разбора — ничего не теряется.
          </p>
        </div>
      </Section>

      <Section title="Чтение почты">
        <div className="space-y-3">
          <div className="flex items-center gap-3">
            <div>
              <div className="mb-1 text-[12px] font-medium text-muted">Интервал опроса, сек</div>
              <Input
                className="w-28 font-mono"
                inputMode="numeric"
                value={interval}
                onChange={(e) => setIntervalSec(e.target.value)}
                onBlur={() => {
                  const n = parseInt(interval, 10);
                  if (!Number.isFinite(n) || n < 30) {
                    toastError("Интервал — целое число, минимум 30 секунд");
                    setIntervalSec(String(settings.poll_interval_sec));
                    return;
                  }
                  if (n !== settings.poll_interval_sec) patch.mutate({ poll_interval_sec: n });
                }}
              />
            </div>
          </div>
          <div>
            <div className="mb-1 text-[12px] font-medium text-muted">
              Домены магазинов и перевозчиков (whitelist — только они уходят в LLM)
            </div>
            <Chips
              values={settings.whitelist_domains}
              onChange={(v) => patch.mutate({ whitelist_domains: v })}
              placeholder="amazon.com, Enter…"
            />
          </div>
          <div>
            <div className="mb-1 text-[12px] font-medium text-muted">
              Домены склада-форвардера (их письма двигают заказ на «Склад США»)
            </div>
            <Chips
              values={settings.forwarder_domains}
              onChange={(v) => patch.mutate({ forwarder_domains: v })}
              placeholder="mywarehouse.com, Enter…"
            />
          </div>
        </div>
      </Section>

      <Section title="Пороги матчинга">
        <div className="flex flex-wrap gap-4 text-[13px]">
          <label className="flex items-center gap-2">
            Автопривязка от
            <Input
              className="w-20 font-mono"
              defaultValue={settings.auto_threshold}
              onBlur={(e) => {
                const n = parseInt(e.target.value, 10);
                if (!Number.isFinite(n)) {
                  toastError("Порог — целое число");
                  e.target.value = String(settings.auto_threshold);
                  return;
                }
                if (n !== settings.auto_threshold) patch.mutate({ auto_threshold: n });
              }}
            />
            баллов
          </label>
          <label className="flex items-center gap-2">
            Подсказки от
            <Input
              className="w-20 font-mono"
              defaultValue={settings.suggest_threshold}
              onBlur={(e) => {
                const n = parseInt(e.target.value, 10);
                if (!Number.isFinite(n)) {
                  toastError("Порог — целое число");
                  e.target.value = String(settings.suggest_threshold);
                  return;
                }
                if (n !== settings.suggest_threshold) patch.mutate({ suggest_threshold: n });
              }}
            />
            баллов
          </label>
        </div>
      </Section>

      <Card className="p-3.5 text-[12px] leading-relaxed text-muted">
        Пароль входа и секреты задаются в файле <span className="font-mono">.env</span> (APP_PASSWORD,
        SECRET_KEY, ключи Google и OpenRouter) и применяются при перезапуске:{" "}
        <span className="font-mono">make up</span>.
      </Card>
    </div>
  );
}
