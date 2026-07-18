"""Evaluate the real YuNet/SFace pipeline on an authorized local dataset.

Expected layout::

    dataset/
      references/<student-id>/*.jpg
      queries/<student-id>/*.jpg
      queries/_unknown/*.jpg

No images leave the machine. The command reports detection failures, closed/open
set identification accuracy, false matches, and ambiguous cases.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

import cv2
import numpy as np

from app.config import settings
from app.matching import cosine_distance
from app.vision.pipeline import AnonymizationPipeline, SFACE_EMBEDDING_MODEL

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}


def _images(directory: Path) -> List[Path]:
    return sorted(path for path in directory.rglob("*") if path.suffix.lower() in IMAGE_SUFFIXES)


def _embedding(pipeline: AnonymizationPipeline, path: Path) -> Tuple[Sequence[float] | None, str | None]:
    image = cv2.imread(str(path))
    if image is None:
        return None, "decode_failed"
    regions = pipeline.analyze(image)
    if len(regions) != 1:
        return None, f"faces_detected_{len(regions)}"
    if regions[0].embedding_model != SFACE_EMBEDDING_MODEL:
        return None, "sface_not_active"
    return regions[0].embedding, None


def evaluate(dataset: Path) -> dict:
    pipeline = AnonymizationPipeline()
    templates: Dict[str, List[Sequence[float]]] = {}
    failures: List[dict] = []
    for path in _images(dataset / "references"):
        label = path.parent.name
        vector, error = _embedding(pipeline, path)
        if error:
            failures.append({"path": str(path), "stage": "reference", "error": error})
        else:
            templates.setdefault(label, []).append(vector)
    if not templates:
        raise RuntimeError("No usable reference templates were found")

    totals = {"known": 0, "unknown": 0, "correct": 0, "false_match": 0, "missed": 0, "ambiguous": 0}
    distances: Dict[str, List[float]] = {"genuine": [], "impostor": []}
    for path in _images(dataset / "queries"):
        expected = path.parent.name
        is_unknown = expected.startswith("_")
        totals["unknown" if is_unknown else "known"] += 1
        vector, error = _embedding(pipeline, path)
        if error:
            totals["missed"] += 1
            failures.append({"path": str(path), "stage": "query", "error": error})
            continue
        ranked = sorted(
            (
                min(cosine_distance(vector, template) for template in student_templates),
                student_id,
            )
            for student_id, student_templates in templates.items()
        )
        best_distance, predicted = ranked[0]
        runner_up = ranked[1][0] if len(ranked) > 1 else float("inf")
        within = best_distance <= settings.sface_match_threshold
        ambiguous = within and runner_up - best_distance < settings.match_min_margin
        if ambiguous:
            totals["ambiguous"] += 1
        if is_unknown:
            distances["impostor"].append(best_distance)
            if within:
                totals["false_match"] += 1
        else:
            own_distance = min(
                cosine_distance(vector, template) for template in templates.get(expected, [])
            ) if expected in templates else float("inf")
            distances["genuine"].append(own_distance)
            if within and not ambiguous and predicted == expected:
                totals["correct"] += 1

    known_evaluated = max(1, totals["known"] - sum(1 for item in failures if item["stage"] == "query" and not Path(item["path"]).parent.name.startswith("_")))
    unknown_evaluated = max(1, totals["unknown"] - sum(1 for item in failures if item["stage"] == "query" and Path(item["path"]).parent.name.startswith("_")))

    def stats(values: List[float]) -> dict:
        return {} if not values else {
            "count": len(values),
            "median": round(float(np.median(values)), 4),
            "p95": round(float(np.percentile(values, 95)), 4),
            "min": round(float(np.min(values)), 4),
            "max": round(float(np.max(values)), 4),
        }

    return {
        "configuration": {
            "match_threshold": settings.sface_match_threshold,
            "minimum_margin": settings.match_min_margin,
            "students": len(templates),
            "templates": sum(len(values) for values in templates.values()),
        },
        "metrics": {
            **totals,
            "known_identification_rate": round(totals["correct"] / known_evaluated, 4),
            "unknown_false_match_rate": round(totals["false_match"] / unknown_evaluated, 4),
        },
        "distance_distributions": {
            "genuine": stats(distances["genuine"]),
            "nearest_unknown": stats(distances["impostor"]),
        },
        "failures": failures,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", type=Path, help="Authorized local evaluation dataset")
    parser.add_argument("--output", type=Path, help="Optional JSON report path")
    args = parser.parse_args()
    report = evaluate(args.dataset.resolve())
    rendered = json.dumps(report, indent=2)
    print(rendered)
    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
