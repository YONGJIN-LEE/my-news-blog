#!/usr/bin/env python3
"""
Python 정적 사이트 빌더 — Apple-inspired Design
content/posts/*.md → public/*.html
"""

import os
import re
import json
from pathlib import Path
from datetime import datetime

SCRIPT_DIR = Path(__file__).parent.resolve()
BLOG_DIR = SCRIPT_DIR.parent
CONTENT_DIR = BLOG_DIR / "content" / "posts"
PUBLIC_DIR = BLOG_DIR / "public"
STATIC_DIR = BLOG_DIR / "static"
CSS_FILE = STATIC_DIR / "css" / "style.css"

SITE_TITLE = "오늘의 뉴스 브리핑"


# ─── Markdown → HTML ──────────────────────────────────────────────────────────
def md_to_html(text):
    lines = text.split("\n")
    html_lines = []
    in_ul = False
    in_ol = False

    for line in lines:
        stripped = line.strip()

        if stripped.startswith("### "):
            if in_ul: html_lines.append("</ul>"); in_ul = False
            html_lines.append(f'<h3>{inline_fmt(stripped[4:])}</h3>')
        elif stripped.startswith("## "):
            if in_ul: html_lines.append("</ul>"); in_ul = False
            html_lines.append(f'<h2>{inline_fmt(stripped[3:])}</h2>')
        elif stripped.startswith("# "):
            if in_ul: html_lines.append("</ul>"); in_ul = False
            html_lines.append(f'<h1>{inline_fmt(stripped[2:])}</h1>')
        elif re.match(r"!\[([^\]]*)\]\(([^)]+)\)", stripped):
            m = re.match(r"!\[([^\]]*)\]\(([^)]+)\)", stripped)
            if in_ul: html_lines.append("</ul>"); in_ul = False
            html_lines.append(
                f'<figure style="text-align:center;margin:32px 0;">'
                f'<img src="{m.group(2)}" alt="{m.group(1)}" '
                f'style="max-width:100%;border-radius:12px;" loading="lazy">'
                f'</figure>'
            )
        elif stripped.startswith("- "):
            if not in_ul:
                html_lines.append("<ul>")
                in_ul = True
            html_lines.append(f"<li>{inline_fmt(stripped[2:])}</li>")
        elif stripped.startswith("> "):
            if in_ul: html_lines.append("</ul>"); in_ul = False
            html_lines.append(f'<blockquote>{inline_fmt(stripped[2:])}</blockquote>')
        elif stripped in ("---", "***"):
            if in_ul: html_lines.append("</ul>"); in_ul = False
            html_lines.append("<hr>")
        elif stripped == "":
            if in_ul:
                html_lines.append("</ul>")
                in_ul = False
        else:
            if in_ul:
                html_lines.append("</ul>")
                in_ul = False
            html_lines.append(f"<p>{inline_fmt(stripped)}</p>")

    if in_ul:
        html_lines.append("</ul>")

    return "\n".join(html_lines)


def inline_fmt(text):
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"\*(.+?)\*", r"<em>\1</em>", text)
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', text)
    text = re.sub(r"`(.+?)`", r"<code>\1</code>", text)
    return text


# ─── Front Matter ─────────────────────────────────────────────────────────────
def parse_front_matter(content):
    meta = {}
    body = content
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            fm = parts[1].strip()
            body = parts[2].strip()
            for line in fm.split("\n"):
                if ":" in line:
                    key, val = line.split(":", 1)
                    key = key.strip()
                    val = val.strip().strip('"').strip("'")
                    if val.startswith("[") and val.endswith("]"):
                        try:
                            val = json.loads(val)
                        except:
                            pass
                    meta[key] = val
    return meta, body


# ─── HTML Templates (Apple-inspired) ─────────────────────────────────────────
def get_css():
    if CSS_FILE.exists():
        return CSS_FILE.read_text(encoding="utf-8")
    return ""


def html_head(title, description="", thumbnail="", is_article=False):
    css = get_css()
    og_type = "article" if is_article else "website"
    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title}</title>
  <meta name="description" content="{description}">
  <meta property="og:title" content="{title}">
  <meta property="og:description" content="{description}">
  {"" if not thumbnail else f'<meta property="og:image" content="{thumbnail}">'}
  <meta property="og:type" content="{og_type}">
  <link rel="preconnect" href="https://cdn.jsdelivr.net">
  <style>{css}</style>
</head>
<body>"""


def html_header():
    return f"""
  <header class="site-header">
    <div class="container">
      <a href="index.html" class="site-title">{SITE_TITLE}</a>
      <nav>
        <a href="index.html">최신</a>
      </nav>
    </div>
  </header>"""


def html_footer():
    return f"""
  <footer class="site-footer">
    <div class="container">
      <p>&copy; {datetime.now().year} {SITE_TITLE}</p>
    </div>
  </footer>
</body>
</html>"""


def render_post(meta, body_html):
    title = meta.get("title", "")
    date_str = meta.get("date", "")[:10]
    category = meta.get("category", "")
    tags = meta.get("tags", [])
    thumbnail = meta.get("thumbnail", "")

    if isinstance(tags, str):
        try: tags = json.loads(tags)
        except: tags = []

    tags_html = " ".join(f'<span class="tag">#{t}</span>' for t in tags) if tags else ""
    tags_footer = " ".join(f'<a class="tag">#{t}</a>' for t in tags) if tags else ""

    hero = ""
    if thumbnail:
        hero = f"""
      <div class="post-hero">
        <img src="{thumbnail}" alt="{title}" loading="lazy">
      </div>"""

    return f"""{html_head(f"{title} — {SITE_TITLE}", title, thumbnail, True)}
{html_header()}
  <main class="container">
    <article class="post-single">
      <header class="post-header">
        <span class="post-category">{category}</span>
        <h1>{title}</h1>
        <div class="post-meta">
          <time>{date_str}</time>
          <div class="post-tags">{tags_html}</div>
        </div>
      </header>
      {hero}
      <div class="post-content">
        {body_html}
      </div>
      <footer class="post-footer">
        <div class="post-tags-footer">{tags_footer}</div>
      </footer>
    </article>
  </main>
{html_footer()}"""


def render_index(posts):
    cards = ""
    for i, p in enumerate(posts):
        if i == 0:
            # Featured post (first)
            thumb_html = ""
            if p.get("thumbnail"):
                thumb_html = f'<div class="featured-image"><img src="{p["thumbnail"]}" alt="{p["title"]}" loading="lazy"></div>'
            cards += f"""
    <article class="post-featured">
      <div class="post-meta-top">
        <span class="post-category">{p.get('category', '')}</span>
        <span class="post-date">{p['date'][:10]}</span>
      </div>
      {thumb_html}
      <h2><a href="{p['slug']}.html">{p['title']}</a></h2>
      <p class="post-summary">{p.get('summary', '')}</p>
    </article>"""
        else:
            thumb = ""
            if p.get("thumbnail"):
                thumb = f'''<div class="post-thumb">
              <a href="{p['slug']}.html"><img src="{p['thumbnail']}" alt="{p['title']}" loading="lazy"></a>
            </div>'''

            cards += f"""
    <article class="post-card">
      {thumb}
      <div class="post-info">
        <div class="post-meta-top">
          <span class="post-category">{p.get('category', '')}</span>
          <span class="post-date">{p['date'][:10]}</span>
        </div>
        <h2><a href="{p['slug']}.html">{p['title']}</a></h2>
        <p class="post-summary">{p.get('summary', '')}</p>
      </div>
    </article>"""

    return f"""{html_head(SITE_TITLE, "최신 뉴스를 빠르고 정확하게")}
{html_header()}
  <main class="container">
    <div class="post-list">
      <h1>오늘의 뉴스</h1>
      <p class="post-list-subtitle">최신 뉴스를 빠르고 정확하게 전달합니다.</p>
      {cards}
    </div>
  </main>
{html_footer()}"""


# ─── Build ────────────────────────────────────────────────────────────────────
def build():
    print(f"빌드: {CONTENT_DIR} → {PUBLIC_DIR}")

    if not CONTENT_DIR.exists():
        print("content/posts/ 없음")
        return

    PUBLIC_DIR.mkdir(parents=True, exist_ok=True)

    # static 복사
    if STATIC_DIR.exists():
        import shutil
        for src in STATIC_DIR.rglob("*"):
            if src.is_file():
                dest = PUBLIC_DIR / src.relative_to(STATIC_DIR)
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dest)

    posts = []
    md_files = sorted(CONTENT_DIR.glob("*.md"))
    print(f"  포스트 {len(md_files)}개")

    for md_file in md_files:
        content = md_file.read_text(encoding="utf-8")
        meta, body = parse_front_matter(content)
        if meta.get("draft") == "true":
            continue

        body_html = md_to_html(body)
        slug = meta.get("slug", md_file.stem).strip('"')
        summary = re.sub(r"<[^>]+>", "", body_html)[:180] + "..."

        page_html = render_post(meta, body_html)
        out_path = PUBLIC_DIR / f"{slug}.html"
        out_path.write_text(page_html, encoding="utf-8")

        posts.append({
            "title": meta.get("title", ""),
            "date": meta.get("date", ""),
            "category": meta.get("category", ""),
            "thumbnail": meta.get("thumbnail", ""),
            "slug": slug,
            "summary": summary,
        })

    # 날짜 기준 역순 정렬
    posts.sort(key=lambda x: x["date"], reverse=True)

    index_html = render_index(posts)
    (PUBLIC_DIR / "index.html").write_text(index_html, encoding="utf-8")
    print(f"  완료: {len(posts)}개 포스트, index.html 생성")


if __name__ == "__main__":
    build()
