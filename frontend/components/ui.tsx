"use client";

/**
 * Shared primitives.
 *
 * Everything visual in the app is built from these, so a spacing or colour
 * decision is made once here rather than re-argued on every page.
 */
import { type ReactNode } from "react";
import { type LucideIcon } from "lucide-react";

export function cx(...parts: (string | false | null | undefined)[]) {
  return parts.filter(Boolean).join(" ");
}

/** ₪ with no decimals — cocktail budgets are never argued in agorot. */
export function money(n?: number | null, dash = "—") {
  if (n == null) return dash;
  return "₪" + Math.round(n).toLocaleString("en-US");
}

export function money2(n?: number | null, dash = "—") {
  if (n == null) return dash;
  return "₪" + n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

const TIGHT_UNITS = new Set(["ml", "l", "cl", "g", "kg", "oz"]);

/**
 * Amount + unit. Symbol units sit flush ("45ml"); word units take a space
 * ("540 leaves"), because "540leaves" reads as a typo.
 */
export function amount(value?: number | null, unit?: string | null, round = false) {
  if (value == null) return "\u2014";
  const n = round ? Math.round(value) : value;
  const text = n.toLocaleString("en-US", { maximumFractionDigits: 2 });
  if (!unit) return text;
  return TIGHT_UNITS.has(unit.toLowerCase()) ? `${text}${unit}` : `${text} ${unit}`;
}

// ── Surfaces ────────────────────────────────────────────────────────────────

export function Card({
  children, className, as: As = "div", ...rest
}: { children: ReactNode; className?: string; as?: "div" | "section" | "article" } & Record<string, unknown>) {
  return (
    <As
      className={cx("bg-surface border border-line rounded-[10px]", className)}
      {...rest}
    >
      {children}
    </As>
  );
}

export function PageHeader({
  title, subtitle, actions, meta,
}: { title: string; subtitle?: string; actions?: ReactNode; meta?: ReactNode }) {
  return (
    <header className="flex flex-wrap items-start justify-between gap-x-6 gap-y-3 mb-6">
      <div className="min-w-0">
        <h1 className="text-[22px] font-semibold tracking-[-.015em] text-ink truncate">
          {title}
        </h1>
        {subtitle && <p className="mt-0.5 text-[13.5px] text-ink-3">{subtitle}</p>}
        {meta && <div className="mt-2.5 flex flex-wrap items-center gap-x-4 gap-y-1.5">{meta}</div>}
      </div>
      {actions && (
        <div className="flex items-center gap-2 shrink-0 w-full sm:w-auto justify-end">
          {actions}
        </div>
      )}
    </header>
  );
}

export function MetaItem({ icon: Icon, children }: { icon: LucideIcon; children: ReactNode }) {
  return (
    <span className="inline-flex items-center gap-1.5 text-[13px] text-ink-2">
      <Icon size={14} strokeWidth={1.75} className="text-ink-4 shrink-0" />
      {children}
    </span>
  );
}

// ── Buttons ─────────────────────────────────────────────────────────────────

type BtnProps = {
  children: ReactNode;
  variant?: "primary" | "secondary" | "ghost" | "danger";
  size?: "sm" | "md";
  icon?: LucideIcon;
  className?: string;
} & Record<string, unknown>;

export function Button({
  children, variant = "secondary", size = "md", icon: Icon, className, ...rest
}: BtnProps) {
  const base =
    "inline-flex items-center justify-center gap-1.5 font-medium rounded-lg " +
    "transition-colors disabled:opacity-40 disabled:cursor-not-allowed whitespace-nowrap";
  const sizes = {
    sm: "h-8 px-2.5 text-[13px]",
    md: "h-9 px-3.5 text-[13.5px]",
  }[size];
  const variants = {
    primary: "bg-accent text-white hover:bg-accent-hi",
    secondary: "bg-surface text-ink border border-line-2 hover:bg-sunk",
    ghost: "text-ink-2 hover:bg-sunk hover:text-ink",
    danger: "text-bad hover:bg-bad-soft",
  }[variant];
  return (
    <button className={cx(base, sizes, variants, className)} {...rest}>
      {Icon && <Icon size={size === "sm" ? 14 : 15} strokeWidth={2} />}
      {children}
    </button>
  );
}

// ── Status ──────────────────────────────────────────────────────────────────

const STATUS_TONES: Record<string, string> = {
  DRAFT: "bg-sunk text-ink-2 border-line",
  MENU_PROPOSED: "bg-accent-soft text-accent-hi border-accent-line",
  MENU_APPROVED: "bg-accent-soft text-accent-hi border-accent-line",
  COSTED: "bg-good-soft text-good border-good/25",
  READY_TO_BUY: "bg-good-soft text-good border-good/25",
  COMPLETED: "bg-sunk text-ink-3 border-line",
  OK: "bg-good-soft text-good border-good/25",
  UNDER_BUDGET: "bg-good-soft text-good border-good/25",
  ON_BUDGET: "bg-warn-soft text-warn border-warn/25",
  OVER_BUDGET: "bg-bad-soft text-bad border-bad/25",
};

export function StatusBadge({ status, className }: { status?: string | null; className?: string }) {
  if (!status) return null;
  const tone = STATUS_TONES[status] ?? "bg-warn-soft text-warn border-warn/25";
  return (
    <span
      className={cx(
        "inline-flex items-center h-[22px] px-2 rounded-md border",
        "text-[11px] font-medium tracking-[.01em] whitespace-nowrap",
        tone, className
      )}
    >
      {status.replace(/_/g, " ").toLowerCase().replace(/^./, (c) => c.toUpperCase())}
    </span>
  );
}

// ── Metrics ─────────────────────────────────────────────────────────────────

export function MetricCard({
  label, value, hint, icon: Icon, tone = "neutral", href, onClick,
}: {
  label: string;
  value: ReactNode;
  hint?: ReactNode;
  icon?: LucideIcon;
  tone?: "neutral" | "good" | "warn" | "bad" | "accent";
  href?: string;
  onClick?: () => void;
}) {
  const toneRing = {
    neutral: "border-line",
    good: "border-good/30",
    warn: "border-warn/30",
    bad: "border-bad/30",
    accent: "border-accent-line",
  }[tone];
  const toneText = {
    neutral: "text-ink",
    good: "text-good",
    warn: "text-warn",
    bad: "text-bad",
    accent: "text-accent-hi",
  }[tone];

  const inner = (
    <>
      <div className="flex items-center gap-1.5 mb-2">
        {Icon && <Icon size={14} strokeWidth={1.75} className="text-ink-4" />}
        <span className="text-[11.5px] uppercase tracking-[.07em] text-ink-3 font-medium">
          {label}
        </span>
      </div>
      <div className={cx("text-[26px] leading-none font-semibold tnum tracking-[-.02em]", toneText)}>
        {value}
      </div>
      {hint && <div className="mt-1.5 text-[12.5px] text-ink-3 leading-snug">{hint}</div>}
    </>
  );

  const cls = cx(
    "bg-surface border rounded-[10px] p-4 text-left block",
    toneRing,
    (href || onClick) && "hover:border-line-2 transition-colors cursor-pointer"
  );

  if (href) return <a href={href} className={cls}>{inner}</a>;
  if (onClick) return <button onClick={onClick} className={cls}>{inner}</button>;
  return <div className={cls}>{inner}</div>;
}

// ── Empty / loading ─────────────────────────────────────────────────────────

export function EmptyState({
  icon: Icon, title, body, action,
}: { icon?: LucideIcon; title: string; body?: string; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center text-center py-14 px-6">
      {Icon && (
        <div className="w-10 h-10 rounded-full bg-sunk grid place-items-center mb-3.5">
          <Icon size={18} strokeWidth={1.75} className="text-ink-4" />
        </div>
      )}
      <p className="text-[15px] font-medium text-ink">{title}</p>
      {body && <p className="mt-1 text-[13.5px] text-ink-3 max-w-[34ch] leading-relaxed">{body}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={cx("hh-shimmer rounded-md", className)} />;
}

// ── Sections ────────────────────────────────────────────────────────────────

export function SectionTitle({
  children, hint, right,
}: { children: ReactNode; hint?: string; right?: ReactNode }) {
  return (
    <div className="flex items-end justify-between gap-4 mb-3">
      <div>
        <h2 className="text-[15px] font-semibold text-ink tracking-[-.01em]">{children}</h2>
        {hint && <p className="mt-0.5 text-[12.5px] text-ink-3">{hint}</p>}
      </div>
      {right}
    </div>
  );
}

/** A short explanation of an assumption the system made. Never hidden. */
export function Note({
  tone = "neutral", children, icon: Icon,
}: { tone?: "neutral" | "warn" | "good"; children: ReactNode; icon?: LucideIcon }) {
  const tones = {
    neutral: "bg-sunk border-line text-ink-2",
    warn: "bg-warn-soft border-warn/25 text-warn",
    good: "bg-good-soft border-good/25 text-good",
  }[tone];
  return (
    <div className={cx("flex gap-2.5 rounded-lg border px-3.5 py-2.5 text-[13px] leading-relaxed", tones)}>
      {Icon && <Icon size={15} strokeWidth={1.75} className="shrink-0 mt-[1px]" />}
      <div className="min-w-0">{children}</div>
    </div>
  );
}

/**
 * A compact figure with a label. Four of these across the top of a page are
 * the difference between "an app I opened" and "an app that knows something".
 *
 * Deliberately quieter than MetricCard, which belongs inside one event: these
 * describe the whole account and must not compete with the hero input above
 * them or the event list below.
 */
export function StatTile({
  icon: Icon, label, value, sub, tone = "plain",
}: {
  icon: LucideIcon;
  label: string;
  value: ReactNode;
  sub?: ReactNode;
  tone?: "plain" | "accent" | "good";
}) {
  return (
    <div className="bg-surface border border-line rounded-[12px] px-3.5 py-3 shadow-[var(--shadow-xs)]">
      <div className="flex items-center gap-1.5 mb-1.5">
        <Icon
          size={13}
          strokeWidth={1.75}
          className={cx(
            tone === "accent" ? "text-accent" : tone === "good" ? "text-good" : "text-ink-4"
          )}
        />
        <span className="text-[11px] uppercase tracking-[.06em] text-ink-3 font-medium">
          {label}
        </span>
      </div>
      <div className="text-[21px] font-semibold tracking-[-.02em] text-ink tnum leading-none">
        {value}
      </div>
      {sub && <div className="mt-1 text-[11.5px] text-ink-4 truncate">{sub}</div>}
    </div>
  );
}

/**
 * A pill. Used for prompt suggestions and filters.
 *
 * `as` exists because a suggestion that fills the input is a button, while one
 * that navigates is a link, and the two must look identical while remaining
 * different elements — a link that is really a button is unusable by keyboard
 * and invisible to a screen reader.
 */
export function Chip({
  children, onClick, disabled, active, className,
}: {
  children: ReactNode;
  onClick?: () => void;
  disabled?: boolean;
  active?: boolean;
  className?: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={cx(
        "h-7 px-2.5 rounded-full border text-[12.5px] whitespace-nowrap",
        "transition-colors disabled:opacity-40 disabled:cursor-not-allowed",
        active
          ? "border-accent-line bg-accent-soft text-accent font-medium"
          : "border-line bg-surface text-ink-2 hover:border-line-2 hover:text-ink",
        className
      )}
    >
      {children}
    </button>
  );
}
