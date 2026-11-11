"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useData } from "./data";

const TABS = [
  { href: "/", label: "TODAY", match: (p: string) => p === "/" },
  { href: "/alerts", label: "ALERTS", match: (p: string) => p.startsWith("/alerts") },
  { href: "/research", label: "RESEARCH", match: (p: string) => p.startsWith("/research") },
  { href: "/you", label: "YOU", match: (p: string) => p.startsWith("/you") },
];

export function Tabs() {
  const path = usePathname() || "/";
  const { unread } = useData();
  return (
    <nav className="tabs" aria-label="Main">
      {TABS.map((t) => (
        <Link key={t.href} href={t.href} className={t.match(path) ? "on" : ""}>
          {t.label}
          {t.href === "/alerts" && unread > 0 && <span className="badge">{unread > 99 ? "99+" : unread}</span>}
        </Link>
      ))}
    </nav>
  );
}
