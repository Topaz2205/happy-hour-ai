"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";

const links = [
  { href: "/", label: "Dashboard" },
  { href: "/events/new", label: "Plan Event" },
  { href: "/cocktails", label: "Cocktails" },
  { href: "/suppliers", label: "Suppliers" },
  { href: "/mappings", label: "Mapping" },
];

export default function Nav() {
  const pathname = usePathname();
  return (
    <nav className="bg-amber-900 text-white shadow-lg">
      <div className="max-w-7xl mx-auto px-4 flex items-center justify-between h-14">
        <Link href="/" className="flex items-center gap-2 font-bold text-lg">
          🍹 Happy Hour AI
        </Link>
        <div className="flex gap-4">
          {links.map((l) => (
            <Link
              key={l.href}
              href={l.href}
              className={`text-sm px-3 py-1 rounded transition-colors ${
                pathname === l.href
                  ? "bg-amber-700 text-white"
                  : "text-amber-100 hover:bg-amber-800"
              }`}
            >
              {l.label}
            </Link>
          ))}
        </div>
      </div>
    </nav>
  );
}
