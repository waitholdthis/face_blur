"""The is_final_blurred computed field implements XOR of system + override."""
import pytest

from app.models import DetectedFace


def _face(system: bool, override: bool) -> DetectedFace:
    return DetectedFace(
        media_upload_id="m",
        box_x=0,
        box_y=0,
        box_w=0.1,
        box_h=0.1,
        detection_confidence=0.9,
        transient_embedding=[0.0] * 512,
        is_blurred_by_system=system,
        is_blurred_override=override,
    )


@pytest.mark.parametrize(
    "system,override,expected",
    [
        (False, False, False),  # not flagged, not overridden -> clear
        (True, False, True),    # flagged by system, kept -> blurred
        (True, True, False),    # flagged by system, overridden -> clear (false positive corrected)
        (False, True, True),    # not flagged, overridden -> blurred (false negative corrected)
    ],
)
def test_xor_logic(system, override, expected):
    assert _face(system, override).is_final_blurred is expected
