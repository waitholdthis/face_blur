"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import AppShell from "@/components/AppShell";
import { api, ApiError } from "@/lib/api";
import type { MediaUploadSummary } from "@/lib/types";

export default function DashboardPage() {
  const [media, setMedia] = useState<MediaUploadSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setMedia(await api.listMedia());
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load queue");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const createDemo = async () => {
    setBusy(true);
    setError(null);
    try {
      await api.createDemo();
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to create demo");
    } finally {
      setBusy(false);
    }
  };

  const removeMedia = async (id: string, filename: string) => {
    if (!window.confirm(`Permanently delete ${filename} and its anonymized copy?`)) return;
    setBusy(true);
    setError(null);
    try {
      await api.deleteMedia(id);
      setMedia((current) => current.filter((item) => item.id !== id));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Delete failed");
    } finally {
      setBusy(false);
    }
  };

  const removeAllMedia = async () => {
    if (
      !window.confirm(
        `Permanently delete all ${media.length} uploaded photos and anonymized copies? This cannot be undone.`
      )
    ) return;
    setBusy(true);
    setError(null);
    try {
      await api.deleteAllMedia();
      setMedia([]);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not delete all uploads");
    } finally {
      setBusy(false);
    }
  };

  return (
    <AppShell>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <div>
          <h1 className="page-title">Review Queue</h1>
          <p className="page-sub">Uploaded media awaiting anonymization review.</p>
        </div>
        <div style={{ display: "flex", gap: 10 }}>
          {media.length > 0 && (
            <button className="btn danger" onClick={removeAllMedia} disabled={busy}>
              Delete all uploads
            </button>
          )}
          <button className="btn secondary" onClick={createDemo} disabled={busy}>
            {busy ? "Generating…" : "＋ Generate demo image"}
          </button>
          <Link className="btn" href="/upload">
            Upload media
          </Link>
        </div>
      </div>

      {error && <div className="error" style={{ marginBottom: 16 }}>{error}</div>}

      <div className="card" style={{ padding: 0 }}>
        {loading ? (
          <p className="muted" style={{ padding: 20 }}>
            Loading…
          </p>
        ) : media.length === 0 ? (
          <div style={{ padding: 40, textAlign: "center" }}>
            <p className="muted">
              No media yet. Upload a group photo, or generate a demo image to see the full
              detect → match → blur → review flow.
            </p>
          </div>
        ) : (
          <table>
            <thead>
              <tr>
                <th>File</th>
                <th>Status</th>
                <th>Faces</th>
                <th>Anonymized</th>
                <th>Created</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {media.map((m) => (
                <tr key={m.id}>
                  <td>{m.original_filename}</td>
                  <td>
                    <span className={`badge ${m.workflow_status}`}>{m.workflow_status}</span>
                  </td>
                  <td>{m.face_count}</td>
                  <td>{m.blurred_count}</td>
                  <td className="muted">{new Date(m.created_at).toLocaleString()}</td>
                  <td>
                    <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                      <Link href={`/review/${m.id}`}>Review →</Link>
                      <button
                        className="btn danger"
                        style={{ padding: "4px 10px", fontSize: 13 }}
                        disabled={busy}
                        onClick={() => removeMedia(m.id, m.original_filename)}
                      >
                        Delete
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </AppShell>
  );
}
