"use client";

import React, { useEffect, useRef, useState } from "react";
import { evaluateFinalBlur } from "@/lib/blur";
import type {
  DetectedFace,
  ManualRedactionBox,
  MediaUploadDetail,
  OverrideEntry,
} from "@/lib/types";

interface Props {
  media: MediaUploadDetail;
  onCommit: (overrides: OverrideEntry[], finalize: boolean) => Promise<void>;
  onAddManual?: (box: ManualRedactionBox) => Promise<void>;
  onRemoveManual?: (faceId: string) => Promise<void>;
  onReprocess?: () => Promise<void>;
  onDeleteMedia?: () => Promise<void>;
  committing?: boolean;
}

const confidenceColor: Record<string, string> = {
  HIGH: "#dc2626",
  MEDIUM: "#d97706",
  LOW: "#ca8a04",
  NONE: "#64748b",
};

type Point = { x: number; y: number };

export default function ReviewQueue({
  media,
  onCommit,
  onAddManual,
  onRemoveManual,
  onReprocess,
  onDeleteMedia,
  committing,
}: Props) {
  const [faces, setFaces] = useState<DetectedFace[]>(media.detected_faces);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [dims, setDims] = useState({ width: 0, height: 0 });
  const [drawMode, setDrawMode] = useState(false);
  const [drawStart, setDrawStart] = useState<Point | null>(null);
  const [drawEnd, setDrawEnd] = useState<Point | null>(null);

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

  const pointFromEvent = (event: React.PointerEvent<HTMLDivElement>): Point => {
    const rect = event.currentTarget.getBoundingClientRect();
    return {
      x: Math.max(0, Math.min(1, (event.clientX - rect.left) / rect.width)),
      y: Math.max(0, Math.min(1, (event.clientY - rect.top) / rect.height)),
    };
  };

  const finishDrawing = async (event: React.PointerEvent<HTMLDivElement>) => {
    if (!drawStart || !onAddManual) return;
    const end = pointFromEvent(event);
    const box: ManualRedactionBox = {
      box_x: Math.min(drawStart.x, end.x),
      box_y: Math.min(drawStart.y, end.y),
      box_w: Math.abs(end.x - drawStart.x),
      box_h: Math.abs(end.y - drawStart.y),
    };
    setDrawStart(null);
    setDrawEnd(null);
    if (box.box_w < 0.01 || box.box_h < 0.01) return;
    setDrawMode(false);
    await onAddManual(box);
  };

  const draft = drawStart && drawEnd
    ? {
        left: Math.min(drawStart.x, drawEnd.x) * dims.width,
        top: Math.min(drawStart.y, drawEnd.y) * dims.height,
        width: Math.abs(drawEnd.x - drawStart.x) * dims.width,
        height: Math.abs(drawEnd.y - drawStart.y) * dims.height,
      }
    : null;

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
              title={
                face.review_reason === "MANUAL_REDACTION"
                  ? "Manual redaction"
                  : face.matched_student_name || "Unknown identity"
              }
              onClick={() => {
                setSelectedId(face.id);
                if (face.review_reason !== "MANUAL_REDACTION") toggle(face.id);
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

        {draft && (
          <div
            aria-label="New manual blur area"
            style={{
              position: "absolute",
              ...draft,
              border: "3px dashed #dc2626",
              background: "rgba(220,38,38,0.22)",
              zIndex: 30,
              pointerEvents: "none",
            }}
          />
        )}

        {drawMode && (
          <div
            aria-label="Draw a box around the missed face"
            onPointerDown={(event) => {
              event.currentTarget.setPointerCapture(event.pointerId);
              const point = pointFromEvent(event);
              setDrawStart(point);
              setDrawEnd(point);
            }}
            onPointerMove={(event) => {
              if (drawStart) setDrawEnd(pointFromEvent(event));
            }}
            onPointerUp={finishDrawing}
            style={{
              position: "absolute",
              inset: 0,
              width: `${dims.width}px`,
              height: `${dims.height}px`,
              cursor: "crosshair",
              zIndex: 25,
              touchAction: "none",
            }}
          />
        )}
      </div>

      <div className="card" style={{ flex: "1 1 280px", minWidth: 260 }}>
        <h3 style={{ margin: "0 0 4px" }}>Operational Control Panel</h3>
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "1fr 1fr",
            gap: 8,
            margin: "12px 0 10px",
          }}
        >
          <button
            className={drawMode ? "btn dark" : "btn secondary"}
            disabled={committing || !onAddManual}
            onClick={() => {
              setDrawMode((active) => !active);
              setDrawStart(null);
              setDrawEnd(null);
            }}
          >
            {drawMode ? "Cancel drawing" : "+ Add missed face"}
          </button>
          <button
            className="btn secondary"
            disabled={committing || !onReprocess}
            onClick={onReprocess}
          >
            Re-run detection
          </button>
        </div>
        {drawMode && (
          <p style={{ margin: "0 0 12px", fontSize: 13, color: "#991b1b" }}>
            Drag a tight box around the missed face. It will be blurred immediately.
          </p>
        )}
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
                {selected.review_reason === "MANUAL_REDACTION"
                  ? "Reviewer-added privacy area"
                  : selected.matched_student_name || "Unknown / not in registry"}
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
              {selected.requires_manual_review && (
                <p
                  style={{
                    fontSize: 12,
                    margin: "9px 0 0",
                    padding: "7px 9px",
                    borderRadius: 6,
                    color: selected.review_reason === "AMBIGUOUS_MATCH" ? "#92400e" : "#475569",
                    background: selected.review_reason === "AMBIGUOUS_MATCH" ? "#fef3c7" : "#f1f5f9",
                  }}
                >
                  {selected.review_reason === "AMBIGUOUS_MATCH"
                    ? "Possible registry match — blurred for safety; confirm manually."
                    : "No confident registry match — inspect before finalizing."}
                </p>
              )}
              <button
                className="btn dark"
                style={{ width: "100%", marginTop: 10 }}
                onClick={() => toggle(selected.id)}
              >
                Toggle Blur
              </button>
              {selected.review_reason === "MANUAL_REDACTION" && onRemoveManual && (
                <button
                  className="btn secondary"
                  style={{ width: "100%", marginTop: 8 }}
                  disabled={committing}
                  onClick={async () => {
                    await onRemoveManual(selected.id);
                    setSelectedId(null);
                  }}
                >
                  Remove manual area
                </button>
              )}
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

        {onDeleteMedia && (
          <button
            className="btn danger"
            style={{ width: "100%", marginTop: 16 }}
            disabled={committing}
            onClick={onDeleteMedia}
          >
            Delete uploaded photo
          </button>
        )}

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
