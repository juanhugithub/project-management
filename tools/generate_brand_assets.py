#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从确定的几何参数生成 Windows 多尺寸品牌图标和 PNG 预览。"""

from pathlib import Path

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[1]
ASSET_DIR = ROOT / "assets"
CANVAS_SIZE = 1024


def _orbit_layer(angle: float) -> Image.Image:
    """绘制一条椭圆轨道，再围绕画布中心旋转到指定方向。"""
    layer = Image.new("RGBA", (CANVAS_SIZE, CANVAS_SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    draw.ellipse((232, 398, 792, 626), outline=(255, 255, 255, 235), width=38)
    return layer.rotate(angle, resample=Image.Resampling.BICUBIC, center=(512, 512))


def build_icon() -> Image.Image:
    """生成高分辨率母版，所有 Windows 图标尺寸由该母版统一缩放。"""
    image = Image.new("RGBA", (CANVAS_SIZE, CANVAS_SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((32, 32, 992, 992), radius=272, fill=(31, 31, 31, 255))
    for angle in (0, 60, -60):
        image.alpha_composite(_orbit_layer(angle))

    draw = ImageDraw.Draw(image)
    green = (141, 196, 161, 255)
    draw.ellipse((442, 442, 582, 582), fill=green)
    draw.ellipse((754, 476, 826, 548), fill=green)
    draw.ellipse((338, 224, 402, 288), fill=(255, 255, 255, 255))
    draw.ellipse((338, 736, 402, 800), fill=green)
    return image


def main() -> None:
    """写出可审阅 PNG 与包含常用 Windows 分辨率的 ICO。"""
    ASSET_DIR.mkdir(parents=True, exist_ok=True)
    master = build_icon()
    preview = master.resize((256, 256), Image.Resampling.LANCZOS)
    preview.save(ASSET_DIR / "brand-icon.png")
    master.save(
        ASSET_DIR / "brand-icon.ico",
        format="ICO",
        sizes=((16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)),
    )


if __name__ == "__main__":
    main()
