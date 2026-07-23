import numpy as np
import pytest

from privacylens.models import BoundingBox, Detection
from privacylens.redaction import redact_regions


def test_solid_redaction_changes_only_detected_region() -> None:
    image = np.full((10, 10, 3), 255, dtype=np.uint8)
    detection = Detection("face", BoundingBox(2, 3, 7, 8), 1.0)

    result = redact_regions(image, [detection], style="solid")

    assert np.all(result[3:8, 2:7] == 0)
    assert np.all(result[:3] == 255)
    assert np.all(image == 255), "the source image must not be modified"


def test_out_of_bounds_region_is_safely_clipped() -> None:
    image = np.full((5, 5), 255, dtype=np.uint8)
    detection = Detection("face", BoundingBox(-2, -2, 2, 2), 1.0)

    result = redact_regions(image, [detection], style="solid")

    assert np.all(result[:2, :2] == 0)
    assert result[4, 4] == 255


def test_unknown_redaction_style_is_rejected() -> None:
    image = np.zeros((5, 5, 3), dtype=np.uint8)

    with pytest.raises(ValueError, match="unsupported redaction style"):
        redact_regions(image, [], style="erase")


@pytest.mark.parametrize("style", ["blur", "pixelate"])
def test_visual_redaction_styles_change_nonuniform_region(style: str) -> None:
    values = np.arange(12 * 12 * 3, dtype=np.uint8).reshape(12, 12, 3)
    detection = Detection("face", BoundingBox(1, 1, 11, 11), 0.8)

    result = redact_regions(values, [detection], style=style)

    assert not np.array_equal(result[1:11, 1:11], values[1:11, 1:11])
    assert np.array_equal(result[0], values[0])
