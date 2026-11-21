"""Импорт работ ивента из базы Art Event Bot в data/works.json + source/.

Запуск из корня репозитория (база открывается только на чтение):
    python tools/import_bot.py "Z:\\Личное\\SW\\art_event_bot\\event.sqlite3"
    python tools/build.py

Ручные правки (название, скрыть работу, победитель, другая обложка, координаты)
пишутся в data/overrides.json по id работы в боте — они переживают повторный импорт:
    { "213": {"name": "Спящая планета"}, "221": {"hidden": true}, "230": {"featured": true, "cover": 1} }
"""
import argparse, json, os, re, shutil, sqlite3, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "source")
WORKS = os.path.join(ROOT, "data", "works.json")
OVERRIDES = os.path.join(ROOT, "data", "overrides.json")

URL = re.compile(r"https?://\S+")
JUNK_LINE = re.compile(
    r"^(\d+\s*/\s*[\d?]+|№\s*\d+|\d+|работа\s*\d+|\d+\s*работа|!ping|фикс\b.*|подробнее.*по ссылке)$", re.I)
NAME_LINE = re.compile(r"^\s*название\s*:\s*(.+)$", re.I | re.M)

def clean_text(raw, own_link):
    """Убирает хэштеги, счётчики «1/2», !ping, пометки «фикс», ссылки. Возвращает (текст, ссылка на статью)."""
    article = None
    for u in URL.findall(raw or ""):
        u = u.rstrip(").,»")
        if u != own_link and not article:
            article = u
    lines = []
    for ln in (raw or "").splitlines():
        ln = URL.sub("", re.sub(r"#\w+", "", ln)).strip(" \t-—:←")
        ln = ln.replace("\xa0", " ").strip()
        if JUNK_LINE.match(ln):
            continue
        lines.append(ln)
    text = re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()
    return text, article

def guess_name(text):
    m = NAME_LINE.search(text)
    if m:
        return m.group(1).strip()
    for ln in text.splitlines():
        ln = ln.strip()
        if not ln:
            continue
        # короткая первая строка — почти всегда название
        if len(ln) <= 48 and not ln.endswith((".", "!", "?")):
            return re.sub(r"^планета\s+", "", ln, flags=re.I).strip(' "«»') or ln
        return ""
    return ""

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("db")
    ap.add_argument("--event", default="ad_mundos", help="slug ивента в боте")
    a = ap.parse_args()
    bot_root = os.path.dirname(os.path.abspath(a.db))
    con = sqlite3.connect(f"file:{a.db}?mode=ro", uri=True)
    ev = con.execute("SELECT id, title FROM events WHERE slug=?", (a.event,)).fetchone()
    if not ev:
        sys.exit(f"Ивент {a.event!r} не найден в базе")
    overrides = json.load(open(OVERRIDES, encoding="utf-8")) if os.path.exists(OVERRIDES) else {}

    works, report = [], []
    for wid, author, link, caption in con.execute(
            "SELECT id, author, link, caption FROM works WHERE event_id=? ORDER BY id", (ev[0],)):
        ov = overrides.get(str(wid), {})
        if ov.get("hidden"):
            continue
        # полный текст поста лежит в import_items (в works.caption он обрезан)
        texts = [t for (t,) in con.execute(
            "SELECT text FROM import_items WHERE committed_work_id=? AND text IS NOT NULL AND text<>'' "
            "ORDER BY tg_message_id", (wid,))]
        raw = max(texts + [caption or ""], key=len)
        text, article = clean_text(raw, link)
        if not article and caption:  # ссылка могла остаться только в подписи
            article = clean_text(caption, link)[1]
        imgs = [p for (p,) in con.execute(
            "SELECT local_path FROM work_images WHERE work_id=? ORDER BY position", (wid,))]
        if not imgs:
            report.append(f"{wid}: нет картинок — пропущена"); continue
        files = []
        os.makedirs(os.path.join(SRC, str(wid)), exist_ok=True)
        for i, p in enumerate(imgs):
            src = os.path.join(bot_root, p)
            rel = f"{wid}/{i}{os.path.splitext(p)[1].lower() or '.jpg'}"
            dst = os.path.join(SRC, rel)
            if not os.path.exists(src):
                report.append(f"{wid}: нет файла {p}"); continue
            if not os.path.exists(dst) or os.path.getsize(dst) != os.path.getsize(src):
                shutil.copyfile(src, dst)
            files.append(rel)
        cover = min(int(ov.get("cover", 0)), len(files) - 1)
        guessed = guess_name(text)
        name = ov.get("name") or guessed
        first = text.split("\n", 1)
        if guessed and first[0].strip().strip(' "«»').endswith(guessed):  # название не дублируем в описании
            text = first[1].strip() if len(first) > 1 else ""
        if not name:
            report.append(f"{wid} {author}: название не найдено — задай в overrides.json")
        works.append({
            "id": f"w{wid}", "file": files[cover],
            "gallery": [f for i, f in enumerate(files) if i != cover],
            "name": name or "Без названия", "author": author or "",
            "description": ov.get("description", text), "link": link or "", "article": article or "",
            "group": ov.get("group", ""), "featured": bool(ov.get("featured")),
            **{k: ov[k] for k in ("x", "y", "size") if k in ov},
        })
    os.makedirs(os.path.dirname(WORKS), exist_ok=True)
    json.dump(works, open(WORKS, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"{ev[1]}: {len(works)} работ → data/works.json")
    for r in report:
        print("  !", r)

if __name__ == "__main__":
    main()
