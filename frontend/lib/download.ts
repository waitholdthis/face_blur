import { api, ApiError } from "./api";
import type { MediaUploadDetail } from "./types";

/** Build a safe download filename from the original upload name. */
export function anonymizedFilename(original: string): string {
  const base = (original || "")
    .replace(/\.[^.]+$/, "")
    .replace(/[^\w-]+/g, "_")
    .replace(/^_+|_+$/g, "");
  return `${base || "photo"}_anonymized.jpg`;
}

/** Download the anonymized render of an already-loaded media detail. */
export async function saveAnonymizedRender(media: MediaUploadDetail): Promise<void> {
  if (!media.processed_url) {
    throw new ApiError(404, "No anonymized render is available for this photo yet");
  }
  const res = await fetch(media.processed_url);
  if (!res.ok) {
    throw new ApiError(res.status, "Could not fetch the anonymized image");
  }
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  try {
    const link = document.createElement("a");
    link.href = url;
    link.download = anonymizedFilename(media.original_filename);
    document.body.appendChild(link);
    link.click();
    link.remove();
  } finally {
    URL.revokeObjectURL(url);
  }
}

/** Fetch a media detail by id, then download its anonymized render. */
export async function downloadAnonymizedRender(mediaId: string): Promise<void> {
  const detail = await api.getMedia(mediaId);
  await saveAnonymizedRender(detail);
}
