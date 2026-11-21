"""Подготовка картинок планет: уменьшение и мягкое затемнение краёв в чёрное.
Чёрный цвет на карте становится прозрачным (режим screen), поэтому края картинки исчезают.
Использование: python tools/prepare.py исходник.jpg img/имя.jpg [сила_маски 0..1]
"""
import sys
from PIL import Image, ImageDraw, ImageFilter, ImageChops

def prepare(src, dst, strength=0.0, max_side=1024):
    im = Image.open(src).convert("RGB")
    im.thumbnail((max_side, max_side), Image.LANCZOS)
    w, h = im.size
    # эллиптическая маска: внутри белая, к краям плавно уходит в чёрный
    pad = int(min(w, h) * (0.06 + 0.12 * strength))
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).ellipse([pad, pad, w - pad, h - pad], fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(min(w, h) * (0.06 + 0.06 * strength)))
    out = ImageChops.multiply(im, Image.merge("RGB", [mask] * 3))
    if strength > 0:  # приглушить светлый фон (для работ не на чёрном)
        out = out.point(lambda v: max(0, int((v - 40 * strength) * (1 + 0.15 * strength))))
    out.save(dst, "JPEG", quality=86, optimize=True, progressive=True)
    print(dst, out.size)

if __name__ == "__main__":
    prepare(sys.argv[1], sys.argv[2], float(sys.argv[3]) if len(sys.argv) > 3 else 0.0)
