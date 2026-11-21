"""Сборка галактики: source/ + data/works.json  ->  img/*.jpg + planets.js

Запуск из корня репозитория:
    python tools/build.py
    python tools/build.py --force          # пересобрать все картинки
    python tools/build.py --seed 42        # другая случайная раскладка

works.json — список работ:
[
  {
    "id": "p01",                  # необязательно, по умолчанию имя файла
    "file": "p01.jpg",            # файл в папке source/
    "name": "Название планеты",
    "author": "Автор",
    "description": "Текст описания",
    "link": "https://t.me/...",   # пост с хэштегом
    "group": "День 1",            # рукав галактики (тема/день); пусто = общая спираль
    "featured": false,            # true = ближе к ядру (например, победители)
    "size": null,                 # ручной размер; по умолчанию случайный 420–620
    "x": null, "y": null          # ручные координаты, перекрывают раскладку
  }
]
Зависимость: Pillow (pip install pillow).
"""
import argparse, hashlib, json, math, os, random, re, sys
from PIL import Image, ImageChops, ImageDraw, ImageFilter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC, IMG = os.path.join(ROOT, "source"), os.path.join(ROOT, "img")
WORKS, OUT = os.path.join(ROOT, "data", "works.json"), os.path.join(ROOT, "planets.js")

TITLE, SUBTITLE = "Ad mundos novos", "Галактика миров участников"
GAP = 40          # минимальный зазор между планетами
ARM_TURN = 3.2    # закрутка рукавов, радиан

# ---------- картинки ----------
def border_brightness(im):
    g = im.convert("L"); w, h = g.size
    pts = [(x, y) for x in range(0, w, 8) for y in (2, h - 3)] + [(x, y) for y in range(0, h, 8) for x in (2, w - 3)]
    return sum(g.getpixel(p) for p in pts) / len(pts)

def prepare(src, dst, max_side=1024):
    """Уменьшает и мягко гасит края в чёрное. Светлый фон приглушается сильнее."""
    im = Image.open(src).convert("RGB")
    im.thumbnail((max_side, max_side), Image.LANCZOS)
    strength = 1.0 if border_brightness(im) > 30 else 0.0
    w, h = im.size
    pad = int(min(w, h) * (0.06 + 0.12 * strength))
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).ellipse([pad, pad, w - pad, h - pad], fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(min(w, h) * (0.06 + 0.06 * strength)))
    out = ImageChops.multiply(im, Image.merge("RGB", [mask] * 3))
    if strength:
        out = out.point(lambda v: max(0, int((v - 40) * 1.15)))
    out.save(dst, "JPEG", quality=86, optimize=True, progressive=True)
    return strength

# ---------- раскладка ----------
def hrand(key, salt):
    """Детерминированное случайное число 0..1 от id — раскладка не прыгает между сборками."""
    return int(hashlib.md5(f"{salt}:{key}".encode()).hexdigest()[:8], 16) / 0xFFFFFFFF

def layout(planets, seed):
    rad = lambda p: p["size"] * 0.42 + GAP / 2
    groups = []
    for p in planets:
        g = p.get("group") or ""
        if g not in groups: groups.append(g)
    free = [p for p in planets if p.get("x") is None or p.get("y") is None]
    # избранные — ближе к ядру
    free.sort(key=lambda p: (not p.get("featured"), hrand(p["id"], seed)))

    if len(groups) >= 2:
        arms = len(groups)
        arm_len = []
        for gi, g in enumerate(groups):
            items = [p for p in free if (p.get("group") or "") == g]
            dist, ds = 260.0, []
            for k, p in enumerate(items):
                dist += rad(p) * (0.6 if k == 0 else 1.15)
                ds.append(dist)
            arm_len.append((gi, items, ds))
        total = max(max(ds) for _, _, ds in arm_len if ds) if any(ds for _, _, ds in arm_len) else 1
        for gi, items, ds in arm_len:
            for p, dist in zip(items, ds):
                t = dist / total
                ang = gi * 2 * math.pi / arms + t * ARM_TURN + (hrand(p["id"], seed + 1) - .5) * 0.12
                off = (hrand(p["id"], seed + 2) - .5) * 120
                r = 120 + t * total + off
                p["x"], p["y"] = math.cos(ang) * r, math.sin(ang) * r * 0.75
    else:
        arms = 3
        golden = math.pi * (3 - math.sqrt(5))
        avg = sum(rad(p) for p in free) / max(1, len(free))
        for k, p in enumerate(free):
            r = avg * 1.9 * math.sqrt(k + 0.6)
            a = k * golden + hrand(p["id"], seed) * 0.3
            p["x"], p["y"] = math.cos(a) * r, math.sin(a) * r * 0.82

    # расталкивание пересечений (ручные координаты не двигаем)
    fixed = {id(p) for p in planets if p not in free}
    for _ in range(300):
        moved = False
        for i, a in enumerate(planets):
            for b in planets[i + 1:]:
                dx, dy = b["x"] - a["x"], b["y"] - a["y"]
                d = math.hypot(dx, dy) or 0.01
                need = rad(a) + rad(b)
                if d < need:
                    push = (need - d) / 2 + 0.5
                    ux, uy = dx / d, dy / d
                    fa, fb = id(a) in fixed, id(b) in fixed
                    ka = 0 if fa else (2 if fb else 1)
                    kb = 0 if fb else (2 if fa else 1)
                    a["x"] -= ux * push * ka; a["y"] -= uy * push * ka
                    b["x"] += ux * push * kb; b["y"] += uy * push * kb
                    moved = True
        if not moved: break
    extent = max((math.hypot(p["x"], p["y"]) + p["size"] / 2 for p in planets), default=1000)
    return arms, extent, groups

# ---------- сборка ----------
def slug(s): return re.sub(r"[^a-zA-Z0-9_-]+", "-", s).strip("-").lower() or "p"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--seed", type=int, default=1)
    args = ap.parse_args()

    works = json.load(open(WORKS, encoding="utf-8"))
    os.makedirs(IMG, exist_ok=True)
    planets, seen = [], set()
    for w in works:
        src = os.path.join(SRC, w["file"])
        if not os.path.exists(src):
            print(f"! нет файла: source/{w['file']} — пропускаю"); continue
        pid = slug(w.get("id") or os.path.splitext(w["file"])[0])
        while pid in seen: pid += "-2"
        seen.add(pid)
        dst = os.path.join(IMG, pid + ".jpg")
        if args.force or not os.path.exists(dst) or os.path.getmtime(dst) < os.path.getmtime(src):
            s = prepare(src, dst)
            print(f"  img/{pid}.jpg" + ("  (светлый фон — приглушён)" if s else ""))
        size = w.get("size") or round(420 + hrand(pid, "size") * 200)
        planets.append({
            "id": pid, "img": f"img/{pid}.jpg", "x": w.get("x"), "y": w.get("y"), "size": size,
            "name": w.get("name") or "Без названия", "author": w.get("author") or "",
            "link": w.get("link") or "", "description": w.get("description") or "",
            "group": w.get("group") or "", "featured": bool(w.get("featured")),
        })

    arms, extent, groups = layout(planets, args.seed)
    for p in planets:
        p["x"], p["y"] = round(p["x"]), round(p["y"])
        if not p["featured"]: p.pop("featured")
        if not p["group"]: p.pop("group")
    data = {"title": TITLE, "subtitle": SUBTITLE, "arms": arms, "radius": round(extent), "planets": planets}
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("// Сгенерировано tools/build.py — правки вносить в data/works.json\n")
        f.write("window.GALAXY = " + json.dumps(data, ensure_ascii=False, indent=2) + ";\n")
    # удалить картинки планет, которых больше нет в works.json
    keep = {p["id"] + ".jpg" for p in planets}
    for f in os.listdir(IMG):
        if f.endswith(".jpg") and f not in keep:
            os.remove(os.path.join(IMG, f)); print(f"  удалено img/{f}")
    print(f"Готово: {len(planets)} планет, рукавов: {arms}, радиус: {round(extent)}")

if __name__ == "__main__":
    sys.exit(main())
