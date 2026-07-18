"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { register } from "@/lib/api";
import { saveToken } from "@/lib/auth";

export default function RegisterPage() {
  const router = useRouter();
  const [schoolName, setSchoolName] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    if (password !== confirm) {
      setError("Passwords do not match");
      return;
    }
    if (password.length < 8) {
      setError("Password must be at least 8 characters");
      return;
    }
    setBusy(true);
    try {
      const token = await register(schoolName, username, password);
      saveToken(token);
      router.push("/dashboard");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not create the account");
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
      <div className="card" style={{ width: 420, maxWidth: "100%" }}>
        <h1 style={{ margin: "0 0 4px", fontSize: 20 }}>🛡️ Create your school account</h1>
        <p className="muted" style={{ marginTop: 0 }}>
          Set up a username and password for your school&apos;s review portal.
        </p>
        <form onSubmit={submit}>
          <label className="label" htmlFor="school-name">School name</label>
          <input
            id="school-name"
            className="input"
            value={schoolName}
            onChange={(e) => setSchoolName(e.target.value)}
            placeholder="Riverdale Elementary"
            required
            minLength={2}
            maxLength={128}
            autoComplete="organization"
          />
          <label className="label" htmlFor="username">Username</label>
          <input
            id="username"
            className="input"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            placeholder="riverdale-elementary"
            required
            minLength={3}
            maxLength={64}
            pattern="[A-Za-z0-9][A-Za-z0-9._-]*"
            title="Letters, numbers, dots, dashes and underscores only"
            autoComplete="username"
          />
          <label className="label" htmlFor="password">Password</label>
          <input
            id="password"
            className="input"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            minLength={8}
            autoComplete="new-password"
          />
          <label className="label" htmlFor="confirm-password">Confirm password</label>
          <input
            id="confirm-password"
            className="input"
            type="password"
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
            required
            minLength={8}
            autoComplete="new-password"
          />
          {error && (
            <div className="error" style={{ marginTop: 14 }}>
              {error}
            </div>
          )}
          <button className="btn" style={{ width: "100%", marginTop: 18 }} disabled={busy}>
            {busy ? "Creating account…" : "Create account"}
          </button>
        </form>
        <p className="muted" style={{ fontSize: 13, marginTop: 16, marginBottom: 0 }}>
          Already have an account? <Link href="/login">Sign in</Link>
        </p>
      </div>
    </div>
  );
}
