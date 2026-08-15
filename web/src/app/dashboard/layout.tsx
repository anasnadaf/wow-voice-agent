"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useSyncExternalStore } from "react";
import { clearToken, hasSession } from "@/lib/api";

const NAV = [
  { href: "/dashboard", label: "Calls" },
  { href: "/dashboard/leads", label: "Leads" },
];

function subscribeToSession(onChange: () => void) {
  window.addEventListener("storage", onChange);
  return () => window.removeEventListener("storage", onChange);
}

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const session = useSyncExternalStore(subscribeToSession, hasSession, () => false);

  useEffect(() => {
    if (!session) router.replace("/login");
  }, [session, router]);

  if (!session) return null;

  const logout = () => {
    clearToken();
    router.replace("/login");
  };

  return (
    <div className="flex min-h-screen flex-col">
      <header className="sticky top-0 z-10 border-b border-line bg-ink/95 backdrop-blur">
        <div className="mx-auto flex w-full max-w-6xl items-center justify-between px-6 py-4">
          <div className="flex items-center gap-8">
            <Link href="/dashboard" className="font-display text-lg tracking-wide text-cream">
              WOW <span className="italic text-brass">Console</span>
            </Link>
            <nav className="flex items-center gap-1">
              {NAV.map(({ href, label }) => {
                const active =
                  href === "/dashboard" ? pathname === "/dashboard" : pathname.startsWith(href);
                return (
                  <Link
                    key={href}
                    href={href}
                    className={`rounded-md px-3 py-1.5 text-sm transition ${
                      active ? "bg-raised text-cream" : "text-stone hover:text-cream"
                    }`}
                  >
                    {label}
                  </Link>
                );
              })}
            </nav>
          </div>
          <button
            onClick={logout}
            className="text-xs uppercase tracking-[0.2em] text-stone transition hover:text-cream"
          >
            Sign out
          </button>
        </div>
      </header>
      <main className="mx-auto w-full max-w-6xl flex-1 px-6 py-8">{children}</main>
    </div>
  );
}
