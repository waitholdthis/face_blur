"use client";

import React, { useEffect, useRef, useState } from "react";
import { evaluateFinalBlur } from "@/lib/blur";
import type { DetectedFace, MediaUploadDetail, OverrideEntry } from "@/lib/types";

interface Props {
  media: MediaUploadDetail;
  onCommit: (overrides: OverrideEntry[], finalize: boolean) => Promise<void>;
  committing?: boolean;
}

const confidenceColor: Record<string, string> = {
  HIGH: "#dc2626",
  MEDIUM: "#d97706",
  LOW: "#ca8a04",
  NONE: "#64748b",
};

export default function ReviewQueue({ media, onCommit, committing }: Props) {
  const [faces, setFaces] = useState<DetectedFace[]>(media.detected_faces);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [dims, setDims] = useState({ width: 0, height: 0 });

  useEffect(() => {
    setFaces(media.detected_faces);
  }, [media]);

  useEffect(() => {
    const handleResize = () => {
      if (containerRef.current) {
        const img = containerRef.current.querySelector("img");
        if (img) setDims({ width: img.clientWidth, height: img.clientHeight });
      }
    };
    window.addEventListener("resize", handleResize);
    const t = setTimeout(handleResize, 150);
    return () => {
      window.removeEventListener("resize", handleResize);
      clearTimeout(t);
    };
  }, [media]);

  const toggle = (id: string) => {
    setFaces((prev) =>
      prev.map((f) =>
        f.id === id ? { ...f, is_blurred_override: !f.is_blurred_override } : f
      )
    );
  };

  const selected = faces.find((f) => f.id === selectedId) || null;

  const commit = (finalize: boolean) => {
    const overrides: OverrideEntry[] = faces.map((f) => ({
      face_id: f.id,
      override_state: f.is_blurred_override,
    }));
    return onCommit(overrides, finalize);
  };

  const blurredCount = faces.filter((f) => evaluateFinalBlur(f)).length;

  return (
    <div style={{ display: "flex", gap: 24, alignItems: "flex-start", flexWrap: "wrap" }}>
      <div
        ref={containerRef}
        className="card"
        style={{ flex: "3 1 520px", position: "relative", padding: 0, overflow: "hidden" }}
      >
        {media.raw_url ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={media.raw_url}
            alt="Review workspace"
            style={{ width: "100%", height: "auto", display: "block" }}
            onLoad={(e) =>
              setDims({
                width: e.currentTarget.clientWidth,
                height: e.currentTarget.clientHeight,
              })
            }
          />
        ) : (
          <div style={{ padding: 40 }} className="muted">
            Raw preview unavailable.
          </div>
        )}

        {faces.map((face) => {
          const blurred = evaluateFinalBlur(face);
          const isSel = face.id === selectedId;
          return (
            <div
              key={face.id}
              title={face.matched_student_name || "Unknown identity"}
              onClick={() => {
                setSelectedId(face.id);
                toggle(face.id);
              }}
              style={{
                position: "absolute",
                left: `${face.box_x * dims.width}px`,
                top: `${face.box_y * dims.height}px`,
                width: `${face.box_w * dims.width}px`,
                height: `${face.box_h * dims.height}px`,
                border: `3px solid ${blurred ? "#e63946" : "#2a9d8f"}`,
                backgroundColor: blurred ? "rgba(230,57,70,0.28)" : "rgba(42,157,143,0.06)",
                backdropFilter: blurred ? "blur(7px)" : "none",
                WebkitBackdropFilter: blurred ? "blur(7px)" : "none",
                cursor: "pointer",
                transition: "all 0.15s ease-in-out",
                boxShadow: isSel ? "0 0 0 3px rgba(37,99,235,0.6)" : "none",
                zIndex: isSel ? 10 : 1,
              }}
            />
          );
        })}
      </div>

      <div className="card" style={{ flex: "1 1 280px", minWidth: 260 }}>
        <h3 style={{ margin: "0 0 4px" }}>Operational Control Panel</h3>
        <p className="muted" style={{ marginTop: 0, fontSize: 13 }}>
          {faces.length} faces detected · {blurredCount} will be anonymized
        </p>

        <div style={{ minHeight: 150, marginBottom: 16 }}>
          {selected ? (
            <div
              style={{
                padding: 14,
                borderRadius: 8,
                background: "#f8fafc",
                border: "1px solid #cbd5e1",
              }}
            >
              <h4 style={{ margin: "0 0 8px" }}>Selected Target</h4>
              <p style={{ fontSize: 13, margin: "4px 0" }}>
                <strong>Identity:</strong>{" "}
                {selected.matched_student_name || "Unknown / not in registry"}
              </p>
              <p style={{ fontSize: 13, margin: "4px 0" }}>
                <strong>Match:</strong>{" "}
                <span style={{ color: confidenceColor[selected.inference_confidence] }}>
                  {selected.inference_confidence}
                </span>
                {selected.cosine_distance_score != null &&
                  ` (d=${selected.cosine_distance_score.toFixed(3)})`}
              </p>
              <p style={{ fontSize: 13, margin: "4px 0" }}>
                <strong>Detection:</strong>{" "}
                {(selected.detection_confidence * 100).toFixed(1)}%
              </p>
              <p style={{ fontSize: 13, margin: "4px 0" }}>
                <strong>Final state:</strong>{" "}
                {evaluateFinalBlur(selected) ? "🔴 Blurred" : "🟢 Visible"}
                {selected.is_blurred_override ? " (overridden)" : ""}
              </p>
              <button
                className="btn dark"
                style={{ width: "100%", marginTop: 10 }}
                onClick={() => toggle(selected.id)}
              >
                Toggle Blur
              </button>
            </div>
          ) : (
            <p className="muted" style={{ fontStyle: "italic", fontSize: 14 }}>
              Select a bounding box to inspect the detection and override the blur decision.
            </p>
          )}
        </div>

        <button
          className="btn"
          style={{ width: "100%", marginBottom: 8 }}
          disabled={committing}
          onClick={() => commit(true)}
        >
          {committing ? "Committing…" : "Commit & Finalize"}
        </button>
        <button
          className="btn secondary"
          style={{ width: "100%" }}
          disabled={committing}
          onClick={() => commit(false)}
        >
          Save Draft (re-render only)
        </button>

        {media.processed_url && (
          <p style={{ marginTop: 14, fontSize: 13 }}>
            <a href={media.processed_url} target="_blank" rel="noreferrer">
              View anonymized render ↗
            </a>
          </p>
        )}
      </div>
    </div>
  );
}
