"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import AppShell from "@/components/AppShell";
import ReviewQueue from "@/components/ReviewQueue";
import { api, ApiError } from "@/lib/api";
import type { MediaUploadDetail, OverrideEntry } from "@/lib/types";

export default function ReviewPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const id = params.id;
  const [media, setMedia] = useState<MediaUploadDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [committing, setCommitting] = useState(false);

  const load = useCallback(async () => {
    try {
      setMedia(await api.getMedia(id));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load media");
    }
  }, [id]);

  useEffect(() => {
    load();
  }, [load]);

  const commit = async (overrides: OverrideEntry[], finalize: boolean) => {
    setCommitting(true);
    setError(null);
    setNotice(null);
    try {
      const res = await api.commitReview(id, overrides, finalize);
      setNotice(
        finalize
          ? `Review finalized. Status: ${res.workflow_status}.`
          : "Draft render updated."
      );
      await load();
      if (finalize) setTimeout(() => router.push("/dashboard"), 1200);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Commit failed");
    } finally {
      setCommitting(false);
    }
  };

  return (
    <AppShell>
      <div style={{ marginBottom: 16 }}>
        <Link href="/dashboard">← Back to queue</Link>
      </div>

      {error && <div className="error" style={{ marginBottom: 16 }}>{error}</div>}
      {notice && <div className="notice" style={{ marginBottom: 16 }}>{notice}</div>}

      {!media ? (
        <p className="muted">Loading…</p>
      ) : (
        <>
          <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 16 }}>
            <h1 className="page-title" style={{ margin: 0 }}>
              {media.original_filename}
            </h1>
            <span className={`badge ${media.workflow_status}`}>{media.workflow_status}</span>
          </div>
          {media.workflow_status === "FAILED" ? (
            <div className="error">Processing failed: {media.error_detail}</div>
          ) : media.detected_faces.length === 0 ? (
            <div className="card">
              <p className="muted">No faces were detected in this image.</p>
            </div>
          ) : (
            <ReviewQueue media={media} onCommit={commit} committing={committing} />
          )}
        </>
      )}
    </AppShell>
  );
}
