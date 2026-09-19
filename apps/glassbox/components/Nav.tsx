"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { api } from "../lib/api";

const LINKS = [
  { href: "/", label: "Timeline" },
  { href: "/approvals", label: "Approvals" },
  { href: "/memory", label: "Memory" },
  { href: "/routing", label: "Routing" },
];

export function Nav() {
  const pathname = usePathname();
  const [pending, setPending] = useState(0);

  // A waiting approval is the one thing worth interrupting someone for, so the
  // count is visible from every screen, not just the approvals one.
  useEffect(() => {
    let cancelled = false;
    const tick = () =>
      api
        .approvals()
        .then((body) => {
          if (!cancelled) setPending(body.approvals.length);
        })
        .catch(() => {
          if (!cancelled) setPending(0);
        });

    tick();
    const timer = setInterval(tick, 3000);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, []);

  return (
    <nav className="nav">
      {LINKS.map((link) => (
        <Link
          key={link.href}
          href={link.href}
          aria-current={pathname === link.href ? "page" : undefined}
        >
          {link.label}
          {link.href === "/approvals" && pending > 0 && (
            <span className="badge" aria-label={`${pending} waiting`}>
              {pending}
            </span>
          )}
        </Link>
      ))}
    </nav>
  );
}
