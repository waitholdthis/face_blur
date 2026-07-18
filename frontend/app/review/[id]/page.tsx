"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import AppShell from "@/components/AppShell";
import ReviewQueue from "@/components/ReviewQueue";
import { api, ApiError } from "@/lib/api";
import type {
  ManualRedactionBox,
  MediaUploadDetail,
  OverrideEntry,
} from "@/lib/types";

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

  useEffect(() => {
    if (media?.workflow_status !== "PENDING" && media?.workflow_status !== "PROCESSING") {
      return;
    }
    const timer = window.setInterval(load, 1500);
    return () => window.clearInterval(timer);
  }, [load, media?.workflow_status]);

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

  const addManualRedaction = async (box: ManualRedactionBox) => {
    setCommitting(true);
    setError(null);
    try {
      setMedia(await api.addManualRedaction(id, box));
      setNotice("Missed face added and blurred. Review the new red box before finalizing.");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not add the blur area");
    } finally {
      setCommitting(false);
    }
  };

  const resizeFace = async (faceId: string, box: ManualRedactionBox) => {
    setCommitting(true);
    setError(null);
    try {
      setMedia(await api.updateFaceBox(id, faceId, box));
      setNotice("Blur area resized and re-rendered.");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not resize the blur area");
    } finally {
      setCommitting(false);
    }
  };

  const removeManualRedaction = async (faceId: string) => {
    setCommitting(true);
    setError(null);
    try {
      setMedia(await api.removeManualRedaction(id, faceId));
      setNotice("Manual blur area removed.");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not remove the blur area");
    } finally {
      setCommitting(false);
    }
  };

  const reprocess = async () => {
    setCommitting(true);
    setError(null);
    setNotice(null);
    try {
      setMedia(await api.reprocessMedia(id));
      setNotice("Detection re-ran with the high-recall face detector.");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Reprocessing failed");
    } finally {
      setCommitting(false);
    }
  };

  const deleteUpload = async () => {
    const filename = media?.original_filename || "this uploaded photo";
    if (!window.confirm(`Permanently delete ${filename} and its anonymized copy?`)) return;
    setCommitting(true);
    setError(null);
    try {
      await api.deleteMedia(id);
      router.push("/dashboard");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Delete failed");
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
          ) : media.workflow_status === "PENDING" || media.workflow_status === "PROCESSING" ? (
            <div className="card">
              <p style={{ margin: "0 0 4px", fontWeight: 700 }}>Analyzing faces…</p>
              <p className="muted" style={{ margin: 0 }}>
                Detection and registry matching are still running. This page will update automatically.
              </p>
            </div>
          ) : (
            <ReviewQueue
              media={media}
              onCommit={commit}
              onAddManual={addManualRedaction}
              onRemoveManual={removeManualRedaction}
              onResizeFace={resizeFace}
              onReprocess={reprocess}
              onDeleteMedia={deleteUpload}
              committing={committing}
            />
          )}
        </>
      )}
    </AppShell>
  );
}
