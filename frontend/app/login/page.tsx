"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { login } from "@/lib/api";
import { saveToken } from "@/lib/auth";

const SHOW_DEMO_LOGIN = process.env.NEXT_PUBLIC_SHOW_DEMO_LOGIN === "1";

export default function LoginPage() {
  const router = useRouter();
  const [username, setUsername] = useState(SHOW_DEMO_LOGIN ? "admin" : "");
  const [password, setPassword] = useState(SHOW_DEMO_LOGIN ? "admin123" : "");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const token = await login(username, password);
      saveToken(token);
      router.push("/dashboard");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div
      style={{
        minHeight: "100vh",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: 24,
      }}
    >
      <div className="card" style={{ width: 380, maxWidth: "100%" }}>
        <h1 style={{ margin: "0 0 4px", fontSize: 20 }}>🛡️ Anonymization Portal</h1>
        <p className="muted" style={{ marginTop: 0 }}>
          Sign in to the human-in-the-loop review console.
        </p>
        <form onSubmit={submit}>
          <label className="label">Username</label>
          <input
            className="input"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            autoComplete="username"
          />
          <label className="label">Password</label>
          <input
            className="input"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password"
          />
          {error && (
            <div className="error" style={{ marginTop: 14 }}>
              {error}
            </div>
          )}
          <button className="btn" style={{ width: "100%", marginTop: 18 }} disabled={busy}>
            {busy ? "Signing in…" : "Sign in"}
          </button>
        </form>
        <p className="muted" style={{ fontSize: 13, marginTop: 16 }}>
          New school? <Link href="/register">Create your account</Link>
        </p>
        {SHOW_DEMO_LOGIN && (
          <p className="muted" style={{ fontSize: 12, marginTop: 8, marginBottom: 0 }}>
            Default demo credentials: <code>admin / admin123</code>
          </p>
        )}
      </div>
    </div>
  );
}
