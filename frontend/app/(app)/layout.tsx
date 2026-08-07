"use client";

import { MobileNav, Sidebar } from "@/components/sidebar";
import { CommandPalette } from "@/components/command-palette";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <>
      <Sidebar />
      <MobileNav />
      <CommandPalette />
      <main className="min-h-screen lg:ml-52">
        <div className="mx-auto max-w-6xl px-4 py-4 pb-[calc(env(safe-area-inset-bottom)+1.25rem)] sm:px-6 sm:py-5">
          {children}
        </div>
      </main>
    </>
  );
}
