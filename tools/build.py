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
import argparse, hashlib, json, math, os, random, re, shutil, sys
from PIL import Image, ImageChops, ImageDraw, ImageFilter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC, IMG = os.path.join(ROOT, "source"), os.path.join(ROOT, "img")
WORKS, OUT = os.path.join(ROOT, "data", "works.json"), os.path.join(ROOT, "planets.js")

TITLE, SUBTITLE = "Ad mundos novos", "Галактика миров участников"
GAP = 40          # минимальный зазор между планетами
ARM_TURN = 3.2    # закрутка рукавов, радиан

# ---------- оформление окрестностей планеты ----------
ARTICLES = os.path.join(ROOT, "data", "articles")
# мотив -> корни слов в названии/описании/статье
MOTIFS = {
    "bubbles":  ["вод", "океан", "мор", "медуз", "пузыр", "волн", "русал", "сирен", "кракен", "водоросл", "течени"],
    "crystals": ["кристалл", "стекл", "самоцвет", "алмаз", "друз", "грани"],
    "embers":   ["огн", "огон", "пламя", "пламен", "лава", "лав", "жар", "раскал", "пепел", "вулкан", "горящ"],
    "snow":     ["снег", "снеж", "мороз", "лёд", "лед", "ледян", "холод", "крио", "метел", "иней"],
    "spores":   ["гриб", "спор", "мицел", "пыльц", "плесен", "лишайн"],
    "petals":   ["цвет", "лепест", "лили", "сад", "роз", "бутон"],
    "sparkles": ["сахар", "сладк", "блест", "сия", "сиян", "звёзд", "звезд", "светящ", "золот", "мерца"],
    "tendrils": ["корн", "корен", "плот", "щупал", "паразит", "вен", "артери", "мышц", "кост", "титан", "плоть"],
    "rings":    ["звук", "музык", "резон", "мелоди", "песн", "акуст", "частот", "сфер"],
    "debris":   ["мусор", "обломк", "руин", "металл", "астероид", "камн", "камен", "осколк", "кольц"],
    "glitch":   ["код", "цифр", "глитч", "данн", "пиксел", "компьют", "двоич", "сигнал", "earth"],
    "hearts":   ["сердц", "сердеч", "любов", "влюб"],
}

def motifs_for(text):
    t = text.lower()
    score = {m: sum(len(re.findall(r"\b" + k, t)) for k in keys) for m, keys in MOTIFS.items()}
    best = [m for m, v in sorted(score.items(), key=lambda kv: -kv[1]) if v > 0][:2]
    return best or ["sparkles"]

def palette_for(path, n=3):
    """Самые насыщенные заметные цвета картинки (без чёрного фона)."""
    import colorsys
    im = Image.open(path).convert("RGB"); im.thumbnail((160, 160))
    q = im.quantize(colors=12, method=Image.Quantize.MEDIANCUT)
    pal = q.getpalette(); counts = sorted(q.getcolors(), reverse=True)
    cand = []
    for cnt, idx in counts:
        r, g, b = pal[idx * 3: idx * 3 + 3]
        h, l, sat = colorsys.rgb_to_hls(r / 255, g / 255, b / 255)
        if l < 0.12: continue
        cand.append((cnt * (0.35 + sat) * (0.4 + min(l, 1 - l) * 2), (r, g, b)))
    cand.sort(reverse=True)
    out, chosen = [], []
    for _, (r, g, b) in cand:
        # чуть ярче и насыщеннее — это свечение
        h, l, sat = colorsys.rgb_to_hls(r / 255, g / 255, b / 255)
        r2, g2, b2 = colorsys.hls_to_rgb(h, max(0.55, min(l, 0.75)), min(1, sat * 1.3 + 0.15))
        rgb = (int(r2 * 255), int(g2 * 255), int(b2 * 255))
        # разные оттенки, а не три почти одинаковых
        if any(sum((x - y) ** 2 for x, y in zip(rgb, o)) < 70 ** 2 for o in chosen): continue
        chosen.append(rgb); out.append("#%02x%02x%02x" % rgb)
        if len(out) == n: break
    return out or ["#b9a6ff"]

def plain_text(html):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html or "")).strip()

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
    order = {p["id"]: i for i, p in enumerate(planets)}
    free.sort(key=lambda p: (not p.get("featured"), order[p["id"]]))

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
MANIFEST = os.path.join(IMG, ".manifest.json")
_manifest = None
def stale(src, dst, force=False):
    """Нужно ли пересобрать dst: сравнение по хэшу исходника, а не по дате (после git checkout даты случайны)."""
    global _manifest
    if _manifest is None:
        _manifest = json.load(open(MANIFEST)) if os.path.exists(MANIFEST) else {}
    h = hashlib.sha1(open(src, "rb").read()).hexdigest()[:16]
    key = os.path.relpath(dst, IMG).replace(os.sep, "/")
    if force or not os.path.exists(dst) or _manifest.get(key) != h:
        _manifest[key] = h
        return True
    return False
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
        if stale(src, dst, args.force):
            s = prepare(src, dst)
            print(f"  img/{pid}.jpg" + ("  (светлый фон — приглушён)" if s else ""))
        cv = os.path.join(IMG, pid, "cover.jpg")
        if stale(src, cv, args.force):
            os.makedirs(os.path.dirname(cv), exist_ok=True)
            im = Image.open(src).convert("RGB"); im.thumbnail((1400, 1400), Image.LANCZOS)
            im.save(cv, "JPEG", quality=84, optimize=True, progressive=True)
        size = w.get("size") or round(420 + hrand(pid, "size") * 200)
        gallery = []
        for k, g in enumerate(w.get("gallery") or []):
            gs = os.path.join(SRC, g)
            if not os.path.exists(gs):
                print(f"! нет файла галереи: source/{g}"); continue
            os.makedirs(os.path.join(IMG, pid), exist_ok=True)
            gd = os.path.join(IMG, pid, f"{k}.jpg")
            if stale(gs, gd, args.force):
                im = Image.open(gs).convert("RGB"); im.thumbnail((1400, 1400), Image.LANCZOS)
                im.save(gd, "JPEG", quality=84, optimize=True, progressive=True)
            gallery.append(f"img/{pid}/{k}.jpg")
        art_path = os.path.join(ARTICLES, pid + ".json")
        art = json.load(open(art_path, encoding="utf-8")) if os.path.exists(art_path) else None
        desc_html = art["html"] if art and art.get("html") and not w.get("descriptionLocked") else ""
        text = " ".join([w.get("name") or "", w.get("description") or "", plain_text(desc_html)])
        motifs = w.get("motifs") or motifs_for(text)
        palette = w.get("palette") or palette_for(dst)
        planets.append({
            "id": pid, "img": f"img/{pid}.jpg", "x": w.get("x"), "y": w.get("y"), "size": size,
            "name": w.get("name") or "Без названия", "author": w.get("author") or "",
            "link": w.get("link") or "", "article": w.get("article") or "",
            "description": "" if desc_html else (w.get("description") or ""),
            "descriptionHtml": desc_html, "gallery": gallery,
            "motifs": motifs, "palette": palette,
            "cover": f"img/{pid}/cover.jpg",
            "group": w.get("group") or "", "featured": bool(w.get("featured")),
        })

    arms, extent, groups = layout(planets, args.seed)
    for p in planets:
        p["x"], p["y"] = round(p["x"]), round(p["y"])
        if not p["featured"]: p.pop("featured")
        if not p["group"]: p.pop("group")
        if not p["gallery"]: p.pop("gallery")
        if not p["article"]: p.pop("article")
        if not p["descriptionHtml"]: p.pop("descriptionHtml")
        if not p["description"]: p.pop("description")
    data = {"title": TITLE, "subtitle": SUBTITLE, "arms": arms, "radius": round(extent), "planets": planets}
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("// Сгенерировано tools/build.py — правки вносить в data/works.json\n")
        f.write("window.GALAXY = " + json.dumps(data, ensure_ascii=False, indent=2) + ";\n")
    # удалить картинки планет, которых больше нет в works.json
    keep = {p["id"] + ".jpg" for p in planets} | {p["id"] for p in planets}
    for f in os.listdir(IMG):
        if f not in keep and f != ".manifest.json":
            fp = os.path.join(IMG, f)
            shutil.rmtree(fp) if os.path.isdir(fp) else os.remove(fp); print(f"  удалено img/{f}")
    if _manifest is not None:
        live = {k: v for k, v in _manifest.items() if os.path.exists(os.path.join(IMG, k))}
        json.dump(live, open(MANIFEST, "w"), indent=0, sort_keys=True)
    print(f"Готово: {len(planets)} планет, рукавов: {arms}, радиус: {round(extent)}")
    for p in planets:
        print(f"  {p['id']:6} {', '.join(p['motifs']):22} {' '.join(p['palette'])}  {p['name'][:40]}")

if __name__ == "__main__":
    sys.exit(main())
