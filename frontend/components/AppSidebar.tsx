"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import {
  Sparkles, CalendarDays, GlassWater, Store, Link2, Settings,
  Menu as MenuIcon, X, PanelLeftClose, PanelLeft,
} from "lucide-react";
import { cx } from "./ui";

const NAV = [
  { href: "/", label: "Home", icon: Sparkles, exact: true },
  { href: "/events", label: "Events", icon: CalendarDays },
  { href: "/cocktails", label: "Cocktails", icon: GlassWater },
  { href: "/suppliers", label: "Suppliers", icon: Store },
  { href: "/mappings", label: "Mappings", icon: Link2 },
];

function isActive(pathname: string, href: string, exact?: boolean) {
  return exact ? pathname === href : pathname === href || pathname.startsWith(href + "/");
}

function NavLinks({ collapsed, onNavigate }: { collapsed: boolean; onNavigate?: () => void }) {
  const pathname = usePathname();
  return (
    <nav className="flex flex-col gap-[2px] px-2">
      {NAV.map(({ href, label, icon: Icon, exact }) => {
        const active = isActive(pathname, href, exact);
        return (
          <Link
            key={href}
            href={href}
            onClick={onNavigate}
            title={collapsed ? label : undefined}
            className={cx(
              "group relative flex items-center gap-2.5 h-[34px] rounded-[8px]",
              "text-[13px] transition-colors",
              collapsed ? "justify-center px-0" : "px-2.5",
              // A left marker and a warm tint, rather than a raised white card.
              // The card treatment competed with the real cards in the content
              // area; this reads as "you are here" without claiming to be an
              // object in its own right.
              active
                ? "bg-accent-soft text-ink font-medium"
                : "text-ink-2 hover:text-ink hover:bg-sunk"
            )}
          >
            {active && !collapsed && (
              <span className="absolute left-0 top-1/2 -translate-y-1/2 w-[2.5px] h-4 rounded-r-full bg-accent" />
            )}
            <Icon
              size={15.5}
              strokeWidth={active ? 2 : 1.75}
              className={active ? "text-accent" : "text-ink-4 group-hover:text-ink-3"}
            />
            {!collapsed && <span className="truncate">{label}</span>}
          </Link>
        );
      })}
    </nav>
  );
}

export default function AppSidebar() {
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);

  const railWidth = collapsed ? "md:w-[56px]" : "md:w-[200px]";

  return (
    <>
      {/* Mobile bar */}
      <div className="md:hidden sticky top-0 z-40 flex items-center justify-between h-13 px-3 py-2.5 bg-canvas/90 backdrop-blur border-b border-line">
        <Link href="/" className="flex items-center gap-2">
          <Logo />
          <span className="text-[14px] font-semibold tracking-[-.01em]">Happy Hour AI</span>
        </Link>
        <button
          onClick={() => setMobileOpen(true)}
          aria-label="Open navigation"
          className="w-9 h-9 grid place-items-center rounded-lg text-ink-2 hover:bg-sunk"
        >
          <MenuIcon size={18} strokeWidth={1.75} />
        </button>
      </div>

      {mobileOpen && (
        <div className="md:hidden fixed inset-0 z-50 flex">
          <button
            aria-label="Close navigation"
            className="absolute inset-0 bg-ink/25"
            onClick={() => setMobileOpen(false)}
          />
          <aside className="relative w-[230px] h-full bg-canvas border-r border-line flex flex-col py-3 hh-rise">
            <div className="flex items-center justify-between px-4 pb-3">
              <div className="flex items-center gap-2">
                <Logo />
                <span className="text-[14px] font-semibold">Happy Hour AI</span>
              </div>
              <button
                onClick={() => setMobileOpen(false)}
                aria-label="Close navigation"
                className="w-8 h-8 grid place-items-center rounded-lg text-ink-3 hover:bg-sunk"
              >
                <X size={17} />
              </button>
            </div>
            <NavLinks collapsed={false} onNavigate={() => setMobileOpen(false)} />
            <div className="mt-auto px-2">
              <SettingsLink collapsed={false} />
            </div>
          </aside>
        </div>
      )}

      {/* Desktop rail */}
      <aside
        className={cx(
          "hidden md:flex flex-col shrink-0 h-screen sticky top-0",
          "border-r border-line bg-canvas transition-[width] duration-200",
          railWidth
        )}
      >
        <div className={cx("flex items-center h-14 shrink-0", collapsed ? "justify-center px-0" : "px-4")}>
          <Link href="/" className="flex items-center gap-2 min-w-0" title="Happy Hour AI">
            <Logo />
            {!collapsed && (
              <span className="text-[14px] font-semibold tracking-[-.012em] truncate">
                Happy Hour AI
              </span>
            )}
          </Link>
        </div>

        <NavLinks collapsed={collapsed} />

        <div className="mt-auto px-2 pb-3 pt-2 flex flex-col gap-[2px] border-t border-line mx-2 mb-0">
          <SettingsLink collapsed={collapsed} />
          <button
            onClick={() => setCollapsed((c) => !c)}
            title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
            className={cx(
              "flex items-center gap-2.5 h-[34px] rounded-[8px] text-[13px] text-ink-3",
              "hover:text-ink hover:bg-sunk transition-colors",
              collapsed ? "justify-center" : "px-2.5"
            )}
          >
            {collapsed ? <PanelLeft size={16} strokeWidth={1.75} /> : <PanelLeftClose size={16} strokeWidth={1.75} />}
            {!collapsed && <span>Collapse</span>}
          </button>
        </div>
      </aside>
    </>
  );
}

function SettingsLink({ collapsed }: { collapsed: boolean }) {
  const pathname = usePathname();
  const active = pathname.startsWith("/settings");
  return (
    <Link
      href="/settings"
      title={collapsed ? "Settings" : undefined}
      className={cx(
        "flex items-center gap-2.5 h-[34px] rounded-[8px] text-[13px] transition-colors",
        collapsed ? "justify-center px-0" : "px-2.5",
        active ? "bg-accent-soft text-ink font-medium" : "text-ink-2 hover:text-ink hover:bg-sunk"
      )}
    >
      <Settings size={15.5} strokeWidth={1.75} className={active ? "text-accent" : "text-ink-4"} />
      {!collapsed && <span>Settings</span>}
    </Link>
  );
}

/**
 * A coupe glass, drawn rather than emoji'd — it has to sit at 20px next to
 * 14px type without looking like a sticker.
 */
function Logo() {
  return (
    <span className="shrink-0 w-[26px] h-[26px] rounded-lg bg-accent grid place-items-center">
      <svg width="14" height="14" viewBox="0 0 16 16" fill="none" aria-hidden="true">
        <path
          d="M2.5 3h11l-4.6 5.2v3.9h2.4a.6.6 0 010 1.2H4.7a.6.6 0 010-1.2h2.4V8.2L2.5 3z"
          fill="#fff"
        />
      </svg>
    </span>
  );
}
