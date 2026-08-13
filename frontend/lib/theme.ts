/** Тема UI: light / dark / system. Выбор хранится в localStorage("theme"),
 * применяется атрибутом data-theme на <html> (см. инлайн-скрипт в layout). */

export type ThemePref = "light" | "dark" | "system";

export const THEME_KEY = "theme";

export function readThemePref(): ThemePref {
  if (typeof window === "undefined") return "system";
  const v = localStorage.getItem(THEME_KEY);
  return v === "light" || v === "dark" ? v : "system";
}

export function applyTheme(pref: ThemePref) {
  const dark =
    pref === "dark" ||
    (pref === "system" && window.matchMedia("(prefers-color-scheme: dark)").matches);
  document.documentElement.dataset.theme = dark ? "dark" : "light";
}

// Тумблеров на странице два (сайдбар и мобильное меню) — общий источник правды
// один: localStorage. Подписчики уведомляются, чтобы подписи не разъезжались.
const listeners = new Set<() => void>();

export function subscribeTheme(cb: () => void): () => void {
  listeners.add(cb);
  return () => {
    listeners.delete(cb);
  };
}

/** Снапшот для useSyncExternalStore; на сервере темы ещё нет — "system". */
export const getThemeSnapshot = readThemePref;
export const getThemeServerSnapshot = (): ThemePref => "system";

export function setThemePref(pref: ThemePref) {
  if (pref === "system") localStorage.removeItem(THEME_KEY);
  else localStorage.setItem(THEME_KEY, pref);
  applyTheme(pref);
  for (const cb of listeners) cb();
}

/** Инлайн-скрипт для layout: ставит тему до первой отрисовки (без вспышки). */
export const THEME_INIT_SCRIPT = `(function(){try{var t=localStorage.getItem("${THEME_KEY}");var d=t==="dark"||(t!=="light"&&matchMedia("(prefers-color-scheme: dark)").matches);document.documentElement.dataset.theme=d?"dark":"light"}catch(e){document.documentElement.dataset.theme="light"}})()`;
