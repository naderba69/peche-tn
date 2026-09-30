"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { BarChart3, FileText, MapPinned, ShieldCheck, Waves } from "lucide-react";

const NAV_ITEMS = [
  { href: "/", label: "تقرير بقعة", icon: FileText },
  { href: "/wilayas", label: "أفضل البقع", icon: MapPinned },
  { href: "/calendar", label: "التقويم", icon: BarChart3 },
  { href: "/bulletin", label: "نشرة INM", icon: ShieldCheck },
] as const;

export function SiteHeader() {
  const pathname = usePathname();
  return (
    <header className="site-header">
      <Link className="brand" href="/" aria-label="Peche TN — الصفحة الرئيسية">
        <span className="brand-mark"><Waves size={23} /></span>
        <span className="brand-copy"><strong>Peche TN</strong><small>قرار البحر، بوضوح</small></span>
      </Link>
      <nav aria-label="التنقل الرئيسي">
        {NAV_ITEMS.map(({ href, label }) => {
          const active = pathname === href;
          return (
            <Link
              key={href}
              href={href}
              className={active ? "active" : undefined}
              aria-current={active ? "page" : undefined}
            >
              {label}
            </Link>
          );
        })}
      </nav>
      <div className="header-badge"><span /> تونس فقط</div>
    </header>
  );
}

export function BottomNav() {
  const pathname = usePathname();
  return (
    <nav className="bottom-nav" aria-label="التنقل السفلي">
      {NAV_ITEMS.map(({ href, label, icon: Icon }) => {
        const active = pathname === href;
        return (
          <Link
            key={href}
            href={href}
            className={active ? "active" : undefined}
            aria-current={active ? "page" : undefined}
          >
            <Icon size={21} />
            <span>{label}</span>
          </Link>
        );
      })}
    </nav>
  );
}
