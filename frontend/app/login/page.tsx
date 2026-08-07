"use client";

import { FormEvent, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { Button, Input } from "@/components/ui";

export default function LoginPage() {
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await api.post("/api/auth/login", { password });
      window.location.href = "/";
    } catch (err) {
      setError(err instanceof ApiError && err.status === 401 ? "Неверный пароль" : "Ошибка входа");
      setBusy(false);
    }
  };

  return (
    <main className="flex min-h-screen items-center justify-center bg-bg p-4">
      <div className="w-full max-w-xs">
        <div className="overflow-hidden rounded-xl border border-line bg-surface shadow-sm">
          <div className="airmail rounded-none" />
          <form onSubmit={submit} className="space-y-4 p-6">
            <div className="flex items-center gap-2.5">
              <img src="/logo.png" alt="" className="size-9 rounded-[8px]" />
              <div>
                <h1 className="text-[17px] font-semibold tracking-tight">
                  sha<span className="text-accent">privezu</span>
                </h1>
                <p className="mt-0.5 text-[12.5px] text-muted">Выкуп в США → доставка клиентам</p>
              </div>
            </div>
            <div>
              <Input
                type="password"
                autoFocus
                placeholder="Пароль"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
              {error && <p className="mt-1.5 text-[12.5px] text-red-600 dark:text-red-400">{error}</p>}
            </div>
            <Button type="submit" variant="primary" className="w-full" disabled={busy || !password}>
              {busy ? "Входим…" : "Войти"}
            </Button>
          </form>
        </div>
      </div>
    </main>
  );
}
