import io

import cv2
import numpy as np
from PIL import Image

from ..schemas import VisualMetrics


METRICS_MAX_SIDE = 1024


def _rgb_image(image: Image.Image) -> Image.Image:
    """将透明插画铺在白底上，避免透明区域在 JPEG 中变黑。"""
    has_alpha = image.mode in {"RGBA", "LA"} or (
        image.mode == "P" and "transparency" in image.info
    )
    if not has_alpha:
        return image.convert("RGB")
    rgba = image.convert("RGBA")
    background = Image.new("RGB", rgba.size, "white")
    background.paste(rgba, mask=rgba.getchannel("A"))
    return background


def _thumbnail(image: Image.Image, max_side: int) -> None:
    """优先让 JPEG 解码器降采样，再缩到分析需要的尺寸。"""
    image.draft("RGB", (max_side, max_side))
    image.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)


def prepare_analysis_image(
    data: bytes, max_side: int = 1600, jpeg_quality: int = 90
) -> tuple[bytes, str]:
    """生成发送给视觉模型的轻量副本；存储中的用户原图保持不变。"""
    with Image.open(io.BytesIO(data)) as image:
        if max(image.size) <= max_side:
            image_format = (image.format or "").lower()
            mime = {
                "jpeg": "image/jpeg",
                "png": "image/png",
                "webp": "image/webp",
            }.get(image_format)
            if mime:
                return data, mime
        _thumbnail(image, max_side)
        rgb = _rgb_image(image)
        output = io.BytesIO()
        # 不启用 optimize，避免 Pillow 为节省少量流量再次增加峰值内存。
        rgb.save(output, format="JPEG", quality=jpeg_quality)
        return output.getvalue(), "image/jpeg"


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
        width, height = image.size
        # 指标只需要全局结构；在受限尺寸上计算可避免 4K/8K 图像产生数百 MB 临时数组。
        _thumbnail(image, METRICS_MAX_SIDE)
        rgb = np.array(_rgb_image(image), dtype=np.uint8)
    sample_height, sample_width = rgb.shape[:2]
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
        focal_x = float(np.mean(x_coords) / max(sample_width - 1, 1))
        focal_y = float(np.mean(y_coords) / max(sample_height - 1, 1))
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
