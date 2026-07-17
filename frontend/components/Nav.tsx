"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { clearToken } from "@/lib/auth";

const links = [
  { href: "/dashboard", label: "Review Queue" },
  { href: "/upload", label: "Upload" },
  { href: "/students", label: "Opt-Out Registry" },
];

export default function Nav() {
  const pathname = usePathname();
  const router = useRouter();

  const logout = () => {
    clearToken();
    router.push("/login");
  };

  return (
    <nav className="nav">
      <span className="brand">🛡️ Anonymization Portal</span>
      {links.map((l) => (
        <Link
          key={l.href}
          href={l.href}
          className={pathname?.startsWith(l.href) ? "active" : ""}
        >
          {l.label}
        </Link>
      ))}
      <span className="spacer" />
      <button onClick={logout}>Sign out</button>
    </nav>
  );
}
