"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { APP_NAME } from "@/lib/format";

const items = [
  { href: "/app", label: "Overview" },
  { href: "/app/niches", label: "Niches" },
  { href: "/app/scripts", label: "Scripts" },
  { href: "/app/videos", label: "Videos" },
  { href: "/app/library", label: "Footage & music" },
  { href: "/app/settings", label: "Plan & channels" },
];

export function NavRail({ email }: { email: string }) {
  const path = usePathname();
  return (
    <nav className="flex shrink-0 flex-col gap-1 border-line md:sticky md:top-0 md:h-screen md:w-56 md:border-r md:py-6 md:pr-4" aria-label="Studio">
      <Link href="/app" className="mb-6 hidden font-display text-2xl font-semibold md:block">{APP_NAME}</Link>
      <ul className="flex gap-1 overflow-x-auto md:flex-col">
        {items.map((it) => {
          const active = it.href === "/app" ? path === "/app" : path.startsWith(it.href);
          return (
            <li key={it.href}>
              <Link
                href={it.href}
                aria-current={active ? "page" : undefined}
                className={`block whitespace-nowrap rounded-md px-3 py-2 text-sm ${active ? "bg-panel text-lamp" : "text-mute hover:text-paper"}`}
              >
                {it.label}
              </Link>
            </li>
          );
        })}
      </ul>
      <div className="mt-auto hidden pt-6 text-xs text-mute md:block">
        <p className="truncate" title={email}>{email}</p>
        <form action="/auth/signout" method="post">
          <button className="mt-1 hover:text-paper">Sign out</button>
        </form>
      </div>
    </nav>
  );
}
