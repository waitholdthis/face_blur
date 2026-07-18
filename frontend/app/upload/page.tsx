"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import AppShell from "@/components/AppShell";
import { api, ApiError } from "@/lib/api";

const MAX_BATCH_FILES = 25;

export default function UploadPage() {
  const router = useRouter();
  const [files, setFiles] = useState<File[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const addFiles = (incoming: File[]) => {
    setError(null);
    setFiles((current) => {
      const unique = new Map(
        current.map((file) => [`${file.name}:${file.size}:${file.lastModified}`, file])
      );
      incoming.forEach((file) =>
        unique.set(`${file.name}:${file.size}:${file.lastModified}`, file)
      );
      const selected = Array.from(unique.values());
      if (selected.length > MAX_BATCH_FILES) {
        setError(`You can upload up to ${MAX_BATCH_FILES} photos at once.`);
      }
      return selected.slice(0, MAX_BATCH_FILES);
    });
  };

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (files.length === 0) return;
    setBusy(true);
    setError(null);
    try {
      const form = new FormData();
      files.forEach((file) => form.append("files", file));
      await api.uploadMediaBatch(form);
      router.push("/dashboard");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Upload failed");
    } finally {
      setBusy(false);
    }
  };

  const totalBytes = files.reduce((total, file) => total + file.size, 0);

  return (
    <AppShell>
      <h1 className="page-title">Upload Group Media</h1>
      <p className="page-sub">
        Select up to {MAX_BATCH_FILES} photos. Each is stored privately, scanned against
        the opt-out registry, and added to the review queue.
      </p>

      <div className="card" style={{ maxWidth: 680 }}>
        <form onSubmit={submit}>
          <label className="label" htmlFor="media-files">Image files (JPEG / PNG)</label>
          <div
            onDragOver={(event) => event.preventDefault()}
            onDrop={(event) => {
              event.preventDefault();
              addFiles(Array.from(event.dataTransfer.files));
            }}
            style={{
              padding: 22,
              border: "2px dashed #94a3b8",
              borderRadius: 10,
              background: "#f8fafc",
              textAlign: "center",
            }}
          >
            <p style={{ margin: "0 0 10px", fontWeight: 700 }}>
              Drop multiple photos here, or choose files
            </p>
            <input
              id="media-files"
              className="input"
              type="file"
              accept="image/*"
              multiple
              onChange={(event) => {
                addFiles(Array.from(event.target.files ?? []));
                event.currentTarget.value = "";
              }}
            />
          </div>

          {files.length > 0 && (
            <div style={{ marginTop: 14 }}>
              <div
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                  marginBottom: 8,
                }}
              >
                <strong>{files.length} photo{files.length === 1 ? "" : "s"} selected</strong>
                <span className="muted">{(totalBytes / (1024 * 1024)).toFixed(1)} MB total</span>
              </div>
              <div
                style={{
                  maxHeight: 240,
                  overflowY: "auto",
                  border: "1px solid #e2e8f0",
                  borderRadius: 8,
                }}
              >
                {files.map((file, index) => (
                  <div
                    key={`${file.name}:${file.size}:${file.lastModified}`}
                    style={{
                      display: "flex",
                      justifyContent: "space-between",
                      alignItems: "center",
                      gap: 12,
                      padding: "9px 11px",
                      borderBottom: index === files.length - 1 ? "none" : "1px solid #e2e8f0",
                    }}
                  >
                    <span style={{ overflow: "hidden", textOverflow: "ellipsis" }}>{file.name}</span>
                    <button
                      type="button"
                      className="btn danger"
                      style={{ padding: "3px 9px", fontSize: 12 }}
                      disabled={busy}
                      onClick={() =>
                        setFiles((current) => current.filter((candidate) => candidate !== file))
                      }
                    >
                      Remove
                    </button>
                  </div>
                ))}
              </div>
            </div>
          )}

          {error && <div className="error" style={{ marginTop: 14 }}>{error}</div>}
          <button className="btn" style={{ marginTop: 18 }} disabled={files.length === 0 || busy}>
            {busy
              ? `Uploading and processing ${files.length} photo${files.length === 1 ? "" : "s"}...`
              : `Upload and process${files.length ? ` ${files.length}` : ""} photo${files.length === 1 ? "" : "s"}`}
          </button>
        </form>
      </div>
    </AppShell>
  );
}
