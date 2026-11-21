"""Скачивает статьи (MelonCherry / melcherry) по ссылкам из data/works.json в data/articles/<id>.json.

    python tools/fetch_articles.py            # только те, которых ещё нет
    python tools/fetch_articles.py --refresh  # перекачать все

Статья берётся из служебного адреса <ссылка>/__data.json (SvelteKit) — это чистые данные без вёрстки.
HTML статьи очищается до безопасного набора тегов; картинки из статьи не берутся
(арты и так есть в галерее), подписи к ним тоже.
Запускается автоматически в GitHub Actions (.github/workflows/build.yml).
"""
import argparse, json, os, re, sys, urllib.request
from html import escape
from html.parser import HTMLParser
from urllib.parse import urlsplit

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORKS = os.path.join(ROOT, "data", "works.json")
OUT = os.path.join(ROOT, "data", "articles")
UA = "Mozilla/5.0 (ad-mundos-novos galaxy; +https://github.com/Ivan3952/ad-mundos-novos)"

# ---------- очистка HTML ----------
KEEP = {"p", "br", "strong", "b", "em", "i", "u", "s", "blockquote", "ul", "ol", "li", "a", "h4", "hr"}
RENAME = {"h1": "h4", "h2": "h4", "h3": "h4", "h5": "h4", "h6": "h4", "del": "s", "strike": "s"}
DROP_WITH_CONTENT = {"figure", "img", "script", "style", "iframe", "video", "audio", "figcaption", "picture"}
VOID = {"br", "hr"}

class Clean(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out, self.skip, self.stack = [], 0, []
    def handle_starttag(self, tag, attrs):
        if tag in DROP_WITH_CONTENT:
            if tag != "img": self.skip += 1
            return
        if self.skip: return
        tag = RENAME.get(tag, tag)
        if tag not in KEEP: return
        if tag == "a":
            href = dict(attrs).get("href") or ""
            if not re.match(r"https?://", href):
                self.stack.append(None); return
            self.out.append(f'<a href="{escape(href)}" target="_blank" rel="noopener nofollow">')
        else:
            self.out.append(f"<{tag}>")
        if tag not in VOID: self.stack.append(tag)
    def handle_startendtag(self, tag, attrs):
        if not self.skip and RENAME.get(tag, tag) in VOID: self.out.append(f"<{RENAME.get(tag, tag)}>")
    def handle_endtag(self, tag):
        if tag in DROP_WITH_CONTENT and tag not in ("img",):
            if self.skip: self.skip -= 1
            return
        if self.skip: return
        tag = RENAME.get(tag, tag)
        if tag not in KEEP or tag in VOID: return
        # закрываем ближайший открытый такой же тег
        for k in range(len(self.stack) - 1, -1, -1):
            if self.stack[k] == tag or (tag == "a" and self.stack[k] is None):
                t = self.stack.pop(k)
                if t: self.out.append(f"</{t}>")
                break
    def handle_data(self, data):
        if not self.skip: self.out.append(escape(data, quote=False))

def clean_html(html):
    c = Clean(); c.feed(html or ""); c.close()
    for t in reversed(c.stack):
        if t: c.out.append(f"</{t}>")
    s = "".join(c.out)
    s = re.sub(r"#AspectusPulchritudinis\b|#Avatar\b", "", s)
    s = re.sub(r"<p>(\s|<br>)*</p>", "", s)                 # пустые абзацы
    s = re.sub(r"<p>(\s*<br>)+", "<p>", s)                  # <br> в начале абзаца
    s = re.sub(r"(<br>\s*)+</p>", "</p>", s)                # и в конце
    s = re.sub(r"(<br>\s*){3,}", "<br><br>", s)
    s = re.sub(r"<(strong|b|em|i|u|s)>\s*</\1>", "", s)
    return s.strip()

def plain(html):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html)).strip()

# ---------- загрузка ----------
def data_url(url):
    p = urlsplit(url)
    return f"{p.scheme}://{p.netloc}{p.path.rstrip('/')}/__data.json"

def fetch(url):
    req = urllib.request.Request(data_url(url), headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        j = json.loads(r.read().decode("utf-8"))
    node = next(n for n in j["nodes"] if n and n.get("type") == "data")
    d = node["data"]
    meta = d[d[0]["article"]]
    val = lambda k: d[meta[k]] if k in meta and isinstance(meta[k], int) else None
    html = clean_html(val("content") or "")
    return {"url": url, "title": val("title") or "", "author": val("authorName") or "", "html": html,
            "chars": len(plain(html))}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true")
    a = ap.parse_args()
    works = json.load(open(WORKS, encoding="utf-8"))
    os.makedirs(OUT, exist_ok=True)
    ok = fail = skip = 0
    for w in works:
        url = (w.get("article") or "").strip()
        if not url or "t.me/" in url: continue
        dst = os.path.join(OUT, w["id"] + ".json")
        if os.path.exists(dst) and not a.refresh:
            skip += 1; continue
        try:
            art = fetch(url)
            json.dump(art, open(dst, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
            print(f"  {w['id']}: «{art['title']}», {art['chars']} символов"); ok += 1
        except Exception as e:
            print(f"  ! {w['id']}: не удалось скачать {url}: {e}"); fail += 1
    print(f"Статьи: скачано {ok}, уже были {skip}, ошибок {fail}")

if __name__ == "__main__":
    sys.exit(main())
