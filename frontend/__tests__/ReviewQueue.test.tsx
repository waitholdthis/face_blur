import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import ReviewQueue from "@/components/ReviewQueue";
import type { MediaUploadDetail } from "@/lib/types";

function makeMedia(): MediaUploadDetail {
  return {
    id: "m1",
    original_filename: "group.jpg",
    workflow_status: "REVIEW_REQUIRED",
    raw_url: "http://example/raw.jpg",
    processed_url: "http://example/out.jpg",
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
    detected_faces: [
      {
        id: "f1",
        box_x: 0.1,
        box_y: 0.1,
        box_w: 0.2,
        box_h: 0.3,
        detection_confidence: 0.98,
        matched_student_id: "s1",
        matched_student_name: "Ava Bennett",
        cosine_distance_score: 0.02,
        inference_confidence: "HIGH",
        is_blurred_by_system: true,
        is_blurred_override: false,
        is_final_blurred: true,
      },
    ],
  };
}

describe("ReviewQueue", () => {
  it("renders detected faces and match info", () => {
    render(<ReviewQueue media={makeMedia()} onCommit={jest.fn()} />);
    expect(screen.getByText(/1 faces detected/)).toBeInTheDocument();
    expect(screen.getByText(/1 will be anonymized/)).toBeInTheDocument();
  });

  it("toggling a face flips its final blur decision (XOR)", async () => {
    render(<ReviewQueue media={makeMedia()} onCommit={jest.fn()} />);
    // Click the bounding box (identified by its title = matched name).
    fireEvent.click(screen.getByTitle("Ava Bennett"));
    // System-flagged + now overridden -> XOR false -> visible.
    expect(await screen.findByText(/🟢 Visible/)).toBeInTheDocument();
    expect(screen.getByText(/0 will be anonymized/)).toBeInTheDocument();
  });

  it("commits overrides with finalize=true", async () => {
    const onCommit = jest.fn().mockResolvedValue(undefined);
    render(<ReviewQueue media={makeMedia()} onCommit={onCommit} />);
    fireEvent.click(screen.getByTitle("Ava Bennett")); // override -> true
    fireEvent.click(screen.getByText("Commit & Finalize"));
    await waitFor(() =>
      expect(onCommit).toHaveBeenCalledWith(
        [{ face_id: "f1", override_state: true }],
        true
      )
    );
  });
});
