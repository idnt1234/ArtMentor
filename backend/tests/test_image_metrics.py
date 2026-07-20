import io

from PIL import Image, ImageDraw

from app.services.image_metrics import compute_visual_metrics, validate_image


def make_test_image() -> bytes:
    image = Image.new("RGB", (320, 200), "#252b44")
    draw = ImageDraw.Draw(image)
    draw.rectangle((170, 30, 300, 170), fill="#efb86a")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def test_visual_metrics_are_normalized() -> None:
    data = make_test_image()
    assert validate_image(data) == (320, 200, "png")
    metrics = compute_visual_metrics(data)
    assert metrics.width == 320
    assert metrics.height == 200
    assert 0 <= metrics.mean_value <= 1
    assert 0 <= metrics.mean_saturation <= 1
    assert len(metrics.palette) == 5
    assert all(color.startswith("#") for color in metrics.palette)

