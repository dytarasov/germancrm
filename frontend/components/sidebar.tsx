"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { cx } from "./ui";

const NAV = [
  { href: "/", label: "Дашборд", icon: "M3 3h7v7H3zM14 3h7v4h-7zM14 10h7v11h-7zM3 13h7v8H3z" },
  { href: "/orders", label: "Заказы", icon: "M21 8l-9-5-9 5 9 5 9-5zM3 8v8l9 5 9-5V8M12 13v8" },
  { href: "/clients", label: "Клиенты", icon: "M16 21v-2a4 4 0 00-4-4H6a4 4 0 00-4 4v2M9 11a4 4 0 100-8 4 4 0 000 8zM22 21v-2a4 4 0 00-3-3.87M16 3.13a4 4 0 010 7.75" },
  { href: "/tracks", label: "Треки", icon: "M4 7h16M4 12h16M4 17h10" },
  { href: "/flights", label: "Рейсы", icon: "M17.8 19.2L16 11l3.5-3.5a2.1 2.1 0 00-3-3L13 8 4.8 6.2a1 1 0 00-.9 1.7L9 12l-2 3H4l-1 1 3 2 2 3 1-1v-3l3-2 4.1 5.1a1 1 0 001.7-.9z" },
  { href: "/money", label: "Деньги", icon: "M12 1v22M17 5H9.5a3.5 3.5 0 000 7h5a3.5 3.5 0 010 7H6" },
  { href: "/mail", label: "Почта", icon: "M4 4h16a2 2 0 012 2v12a2 2 0 01-2 2H4a2 2 0 01-2-2V6a2 2 0 012-2zM22 6l-10 7L2 6" },
  { href: "/settings", label: "Настройки", icon: "M12 15a3 3 0 100-6 3 3 0 000 6zM19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 11-2.83 2.83l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 11-4 0v-.09A1.65 1.65 0 008.6 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 11-2.83-2.83l.06-.06a1.65 1.65 0 00.33-1.82 1.65 1.65 0 00-1.51-1H2a2 2 0 110-4h.09A1.65 1.65 0 003.6 8.6a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 112.83-2.83l.06.06a1.65 1.65 0 001.82.33H8a1.65 1.65 0 001-1.51V2a2 2 0 114 0v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 112.83 2.83l-.06.06a1.65 1.65 0 00-.33 1.82V8a1.65 1.65 0 001.51 1H21a2 2 0 110 4h-.09a1.65 1.65 0 00-1.51 1z" },
];

function Icon({ d, className }: { d: string; className?: string }) {
  return (
    <svg
      className={cx("size-4 shrink-0", className)}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      <path d={d} />
    </svg>
  );
}

function isActive(pathname: string, href: string): boolean {
  return href === "/" ? pathname === "/" : pathname.startsWith(href);
}

async function logout() {
  try {
    await api.post("/api/auth/logout");
  } finally {
    window.location.href = "/login";
  }
}

function Logo() {
  return (
    <span className="flex items-center gap-2 text-[15px] font-semibold tracking-tight">
      <img src="/logo.png" alt="" className="size-5 rounded-[5px]" />
      <span>
        sha<span className="text-accent">privezu</span>
      </span>
    </span>
  );
}

/** Десктопный фиксированный сайдбар (lg+). */
export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="fixed inset-y-0 left-0 z-30 hidden w-52 flex-col border-r border-line bg-surface lg:flex">
      <div className="flex h-14 items-center gap-2 px-4">
        <Logo />
      </div>

      <nav className="flex-1 space-y-0.5 px-2">
        {NAV.map((item) => (
          <Link
            key={item.href}
            href={item.href}
            className={cx(
              "flex h-8.5 items-center gap-2.5 rounded-md px-2.5 text-[13px] font-medium transition-colors",
              isActive(pathname, item.href)
                ? "bg-surface2 text-ink"
                : "text-muted hover:bg-surface2 hover:text-ink",
            )}
          >
            <Icon d={item.icon} />
            {item.label}
          </Link>
        ))}
      </nav>

      <div className="space-y-1 border-t border-line p-2">
        <button
          onClick={() => window.dispatchEvent(new CustomEvent("open-cmdk"))}
          className="flex h-8.5 w-full items-center gap-2.5 rounded-md px-2.5 text-[13px] text-muted transition-colors hover:bg-surface2 hover:text-ink"
        >
          <Icon d="M11 19a8 8 0 100-16 8 8 0 000 16zM21 21l-4.35-4.35" />
          Поиск
          <kbd className="ml-auto rounded border border-line bg-surface2 px-1.5 font-mono text-[10.5px] text-muted">
            ⌘K
          </kbd>
        </button>
        <button
          onClick={logout}
          className="flex h-8.5 w-full items-center gap-2.5 rounded-md px-2.5 text-[13px] text-muted transition-colors hover:bg-surface2 hover:text-ink"
        >
          <Icon d="M9 21H5a2 2 0 01-2-2V5a2 2 0 012-2h4M16 17l5-5-5-5M21 12H9" />
          Выйти
        </button>
      </div>
    </aside>
  );
}

/** Мобильная навигация (<lg): верхняя панель + выезжающий drawer. */
export function MobileNav() {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);

  useEffect(() => setOpen(false), [pathname]);

  return (
    <>
      <header className="sticky top-0 z-30 border-b border-line bg-surface pt-[env(safe-area-inset-top)] lg:hidden">
        <div className="flex h-13 items-center gap-1 px-2">
          <button
            aria-label="Открыть меню"
            onClick={() => setOpen(true)}
            className="flex size-11 items-center justify-center rounded-md text-muted hover:bg-surface2 hover:text-ink"
          >
            <Icon d="M4 6h16M4 12h16M4 18h16" className="size-5" />
          </button>
          <Link href="/">
            <Logo />
          </Link>
          <button
            aria-label="Поиск"
            onClick={() => window.dispatchEvent(new CustomEvent("open-cmdk"))}
            className="ml-auto flex size-11 items-center justify-center rounded-md text-muted hover:bg-surface2 hover:text-ink"
          >
            <Icon d="M11 19a8 8 0 100-16 8 8 0 000 16zM21 21l-4.35-4.35" className="size-5" />
          </button>
        </div>
      </header>

      {open && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <div className="absolute inset-0 bg-black/40" onClick={() => setOpen(false)} aria-hidden />
          <nav className="absolute inset-y-0 left-0 flex h-[100dvh] w-72 max-w-[85vw] flex-col border-r border-line bg-surface pt-[env(safe-area-inset-top)] pb-[env(safe-area-inset-bottom)]">
            <div className="flex h-13 items-center justify-between pr-1 pl-4">
              <Logo />
              <button
                aria-label="Закрыть меню"
                onClick={() => setOpen(false)}
                className="flex size-11 items-center justify-center rounded-md text-[18px] text-muted hover:bg-surface2 hover:text-ink"
              >
                ×
              </button>
            </div>
            <div className="flex-1 space-y-0.5 overflow-y-auto px-2">
              {NAV.map((item) => (
                <Link
                  key={item.href}
                  href={item.href}
                  onClick={() => setOpen(false)}
                  className={cx(
                    "flex h-11 items-center gap-3 rounded-md px-3 text-[14px] font-medium transition-colors",
                    isActive(pathname, item.href)
                      ? "bg-surface2 text-ink"
                      : "text-muted hover:bg-surface2 hover:text-ink",
                  )}
                >
                  <Icon d={item.icon} className="size-4.5" />
                  {item.label}
                </Link>
              ))}
            </div>
            <div className="border-t border-line p-2">
              <button
                onClick={logout}
                className="flex h-11 w-full items-center gap-3 rounded-md px-3 text-[14px] text-muted transition-colors hover:bg-surface2 hover:text-ink"
              >
                <Icon d="M9 21H5a2 2 0 01-2-2V5a2 2 0 012-2h4M16 17l5-5-5-5M21 12H9" className="size-4.5" />
                Выйти
              </button>
            </div>
          </nav>
        </div>
      )}
    </>
  );
}
