"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import AppShell from "@/components/AppShell";
import { api, ApiError } from "@/lib/api";

export default function UploadPage() {
  const router = useRouter();
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!file) return;
    setBusy(true);
    setError(null);
    try {
      const form = new FormData();
      form.append("file", file);
      const res = await api.uploadMedia(form);
      router.push(`/review/${res.media_id}`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Upload failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <AppShell>
      <h1 className="page-title">Upload Group Media</h1>
      <p className="page-sub">
        Group photos are stored privately, scanned against the opt-out registry, and queued
        for anonymization. Only faces matching a no-consent student are blurred.
      </p>

      <div className="card" style={{ maxWidth: 560 }}>
        <form onSubmit={submit}>
          <label className="label">Image file (JPEG / PNG)</label>
          <input
            className="input"
            type="file"
            accept="image/*"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          />
          {file && (
            <p className="muted" style={{ fontSize: 13, marginTop: 8 }}>
              Selected: {file.name} ({Math.round(file.size / 1024)} KB)
            </p>
          )}
          {error && <div className="error" style={{ marginTop: 14 }}>{error}</div>}
          <button className="btn" style={{ marginTop: 18 }} disabled={!file || busy}>
            {busy ? "Uploading & processing…" : "Upload & process"}
          </button>
        </form>
      </div>
    </AppShell>
  );
}
