const usd = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  minimumFractionDigits: 2,
});

export function fmtMoney(v: string | number | null | undefined): string {
  if (v === null || v === undefined || v === "") return "—";
  const n = typeof v === "number" ? v : parseFloat(v);
  if (Number.isNaN(n)) return "—";
  return usd.format(n);
}

const dateFmt = new Intl.DateTimeFormat("ru-RU", { day: "numeric", month: "short" });
const dateFullFmt = new Intl.DateTimeFormat("ru-RU", {
  day: "2-digit",
  month: "2-digit",
  year: "numeric",
});
const dateTimeFmt = new Intl.DateTimeFormat("ru-RU", {
  day: "numeric",
  month: "short",
  hour: "2-digit",
  minute: "2-digit",
});

export function fmtDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso.length === 10 ? iso + "T00:00:00" : iso);
  if (Number.isNaN(d.getTime())) return "—";
  return dateFmt.format(d);
}

export function fmtDateFull(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso.length === 10 ? iso + "T00:00:00" : iso);
  if (Number.isNaN(d.getTime())) return "—";
  return dateFullFmt.format(d);
}

export function fmtDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return dateTimeFmt.format(d);
}

export function fmtMonth(m: string): string {
  // "2026-08" → "август 2026"
  const [y, mo] = m.split("-").map(Number);
  const d = new Date(y, (mo || 1) - 1, 1);
  return new Intl.DateTimeFormat("ru-RU", { month: "long", year: "numeric" }).format(d);
}

/** Локальная дата в YYYY-MM-DD — без UTC-сдвига от toISOString(). */
export function toLocalISO(d: Date): string {
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

export function isoToday(): string {
  return toLocalISO(new Date());
}

/** Разрешаем рендерить <a href> только для http(s) — иначе показываем текстом. */
export function safeHref(url: string | null | undefined): string | null {
  if (!url) return null;
  try {
    const u = new URL(url);
    return u.protocol === "http:" || u.protocol === "https:" ? url : null;
  } catch {
    return null;
  }
}

const TG_USERNAME = /^[A-Za-z][A-Za-z0-9_]{3,31}$/;

/**
 * Telegram клиента пишут как попало: https://t.me/nick, t.me/nick, @nick, nick.
 * Возвращает ссылку и подпись «@nick»; null — если это не похоже на Telegram
 * (тогда показываем как есть, текстом).
 */
export function telegramLink(raw: string | null | undefined): { href: string; label: string } | null {
  const v = (raw ?? "").trim();
  if (!v) return null;
  const m = v.match(/^(?:https?:\/\/)?(?:www\.)?(?:t\.me|telegram\.me)\/([^/?#\s]+)/i);
  if (m) {
    const href = /^https?:\/\//i.test(v) ? v : `https://${v}`;
    if (!safeHref(href)) return null;
    // t.me/+invite и прочие не-юзернеймы показываем ссылкой как есть
    return { href, label: TG_USERNAME.test(m[1]) ? `@${m[1]}` : v.replace(/^https?:\/\//i, "") };
  }
  const nick = v.replace(/^@/, "");
  if (TG_USERNAME.test(nick)) return { href: `https://t.me/${nick}`, label: `@${nick}` };
  // произвольная http(s)-ссылка тоже кликабельна
  return safeHref(v) ? { href: v, label: v.replace(/^https?:\/\//i, "") } : null;
}
