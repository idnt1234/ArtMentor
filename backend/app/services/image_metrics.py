import io

import cv2
import numpy as np
from PIL import Image

from ..schemas import VisualMetrics


def validate_image(data: bytes, max_pixels: int = 30_000_000) -> tuple[int, int, str]:
    try:
        with Image.open(io.BytesIO(data)) as image:
            image.verify()
        with Image.open(io.BytesIO(data)) as image:
            width, height = image.size
            image_format = (image.format or "").lower()
    except Exception as exc:
        raise ValueError("The uploaded file is not a valid image.") from exc
    if width * height > max_pixels:
        raise ValueError("The image is too large. Please stay below 30 megapixels.")
    if image_format not in {"jpeg", "png", "webp"}:
        raise ValueError("Only JPG, PNG and WebP images are supported.")
    return width, height, image_format


def _hex_palette(rgb: np.ndarray, count: int = 5) -> list[str]:
    # 使用缩略图和 k-means 提取主色，避免大图造成不必要的计算开销。
    small = cv2.resize(rgb, (96, 96), interpolation=cv2.INTER_AREA)
    pixels = small.reshape((-1, 3)).astype(np.float32)
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.5)
    _compactness, labels, centers = cv2.kmeans(
        pixels, count, None, criteria, 5, cv2.KMEANS_PP_CENTERS
    )
    frequency = np.bincount(labels.flatten(), minlength=count)
    ordered = centers[np.argsort(frequency)[::-1]].astype(int)
    return ["#{:02X}{:02X}{:02X}".format(*color) for color in ordered]


def compute_visual_metrics(data: bytes) -> VisualMetrics:
    with Image.open(io.BytesIO(data)) as image:
        rgb = np.array(image.convert("RGB"))
    height, width = rgb.shape[:2]
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)

    mean_value = float(gray.mean() / 255)
    contrast = float(gray.std() / 128)
    dark_ratio = float(np.mean(gray < 64))
    light_ratio = float(np.mean(gray > 192))
    mean_saturation = float(hsv[:, :, 1].mean() / 255)

    r, g, b = [rgb[:, :, index].astype(np.float32) for index in range(3)]
    rg = np.abs(r - g)
    yb = np.abs(0.5 * (r + g) - b)
    colorfulness = float(
        (np.sqrt(rg.std() ** 2 + yb.std() ** 2) + 0.3 * np.sqrt(rg.mean() ** 2 + yb.mean() ** 2))
        / 180
    )

    edges = cv2.Canny(gray, 80, 180)
    edge_density = float(np.mean(edges > 0))
    y_coords, x_coords = np.nonzero(edges)
    if len(x_coords):
        focal_x = float(np.mean(x_coords) / max(width - 1, 1))
        focal_y = float(np.mean(y_coords) / max(height - 1, 1))
    else:
        focal_x = focal_y = 0.5
    thirds = [(1 / 3, 1 / 3), (2 / 3, 1 / 3), (1 / 3, 2 / 3), (2 / 3, 2 / 3)]
    thirds_distance = min(
        ((focal_x - tx) ** 2 + (focal_y - ty) ** 2) ** 0.5 for tx, ty in thirds
    )

    return VisualMetrics(
        width=width,
        height=height,
        mean_value=round(mean_value, 3),
        value_contrast=round(contrast, 3),
        dark_ratio=round(dark_ratio, 3),
        light_ratio=round(light_ratio, 3),
        mean_saturation=round(mean_saturation, 3),
        colorfulness=round(colorfulness, 3),
        edge_density=round(edge_density, 3),
        focal_point_x=round(focal_x, 3),
        focal_point_y=round(focal_y, 3),
        thirds_distance=round(float(thirds_distance), 3),
        palette=_hex_palette(rgb),
    )

