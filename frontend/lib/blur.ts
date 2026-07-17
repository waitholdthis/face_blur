import type { DetectedFace } from "./types";

/**
 * Final blur decision = XOR(system, override).
 *
 * Mirrors the backend's generated `is_final_blurred` column so the UI can
 * preview the outcome of a toggle before it is committed:
 *  - system flagged & not overridden  -> blurred
 *  - system flagged & overridden      -> cleared (false positive corrected)
 *  - not flagged & overridden         -> blurred (false negative corrected)
 *  - not flagged & not overridden     -> cleared
 */
export function evaluateFinalBlur(
  face: Pick<DetectedFace, "is_blurred_by_system" | "is_blurred_override">
): boolean {
  return face.is_blurred_by_system !== face.is_blurred_override;
}
