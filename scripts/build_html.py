#!/usr/bin/env python3
"""
Python 정적 사이트 빌더 — Apple-inspired Design
content/posts/*.md → public/*.html
카테고리별 게시판 + 메인 페이지
"""

import os
import re
import json
import unicodedata
from pathlib import Path
from datetime import datetime
from collections import defaultdict


def nfc(s):
    """한글 파일명/URL 정규화 (NFC 완성형)"""
    return unicodedata.normalize("NFC", s) if isinstance(s, str) else s

SCRIPT_DIR = Path(__file__).parent.resolve()
BLOG_DIR = SCRIPT_DIR.parent
CONTENT_DIR = BLOG_DIR / "content" / "posts"
PUBLIC_DIR = BLOG_DIR / "public"
STATIC_DIR = BLOG_DIR / "static"
CSS_FILE = STATIC_DIR / "css" / "style.css"

SITE_TITLE = "오늘의 뉴스 브리핑"

# 페이지당 게시물 수
POSTS_PER_PAGE = 30

# 카테고리 정의 (slug → 표시 이름)
CATEGORIES = {
    "all": "전체",
    "politics": "정치",
    "society": "사회",
    "economy": "경제",
    "entertainment": "연예",
    "life": "생활",
    "it": "IT",
    "sports": "스포츠",
    "fashion": "패션",
}

# 한글 카테고리명 → slug 매핑
CATEGORY_TO_SLUG = {
    "정치": "politics",
    "사회": "society",
    "경제": "economy",
    "연예": "entertainment",
    "생활": "life",
    "IT": "it",
    "스포츠": "sports",
    "패션": "fashion",
    "Sports": "sports",
}


# ─── Markdown → HTML ──────────────────────────────────────────────────────────
def md_to_html(text):
    lines = text.split("\n")
    html_lines = []
    in_ul = False

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
        elif re.match(r"!\[", stripped):
            # 이미지 마크다운: ![alt](url) — alt에 대괄호 포함 가능
            m = re.match(r"!\[(.*?)\]\((\S+)\)", stripped)
            if not m:
                # 더 관대한 매칭: 마지막 ](url) 패턴
                m = re.search(r"\]\((\S+)\)\s*$", stripped)
                if m:
                    alt = re.sub(r"^!\[", "", stripped[:m.start()]).rstrip("]")
                    url = m.group(1)
                else:
                    alt = ""
                    url = ""
            else:
                alt = m.group(1)
                url = m.group(2)
            if url and url.startswith("http"):
                if in_ul: html_lines.append("</ul>"); in_ul = False
                safe_alt = alt.replace('"', '&quot;')[:100]
                html_lines.append(
                    f'<figure style="text-align:center;margin:32px 0;">'
                    f'<img src="{url}" alt="{safe_alt}" '
                    f'style="max-width:100%;border-radius:12px;" loading="lazy">'
                    f'</figure>'
                )
            else:
                continue  # 잘못된 이미지 마크다운은 무시 (평문으로 출력 안 함)
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
  <link rel="preconnect" href="https://cdn.jsdelivr.net" crossorigin>
  <link rel="preconnect" href="https://fonts.googleapis.com" crossorigin>
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <style>{css}</style>
</head>
<body>"""


def category_nav_html(active_slug="all"):
    """카테고리 네비게이션 바 생성"""
    nav_items = ""
    for slug, name in CATEGORIES.items():
        href = "index.html" if slug == "all" else f"category-{slug}.html"
        active = ' class="active"' if slug == active_slug else ""
        nav_items += f'<a href="{href}"{active}>{name}</a>\n        '
    return f"""
  <nav class="category-nav">
    <div class="container">
      {nav_items}
    </div>
  </nav>"""


def popular_sidebar_html():
    """인기글 사이드바 (전체 페이지 좌측, JS로 채움)"""
    return """
  <aside class="popular-sidebar" id="popularSidebar" aria-label="인기 게시물">
    <div class="popular-sidebar-inner">
      <h3 class="popular-title">🔥 인기 게시물</h3>
      <ol class="popular-list" id="popularList">
        <li class="popular-empty">아직 좋아요를 받은 글이 없어요.</li>
      </ol>
    </div>
  </aside>"""


def html_header(active_category="all"):
    return f"""
  <header class="site-header">
    <div class="container">
      <a href="index.html" class="site-title">{SITE_TITLE}</a>
      <nav>
        <a href="index.html">홈</a>
      </nav>
    </div>
  </header>
  {category_nav_html(active_category)}
  {popular_sidebar_html()}"""


def relative_time_script():
    """클라이언트 사이드 상대 시간 표시 스크립트"""
    return """
<script>
(function(){
  function relTime(dateStr){
    var d = dateStr.includes('T') ? new Date(dateStr + '+09:00') : new Date(dateStr + 'T09:00:00+09:00');
    var now = new Date();
    var diff = Math.floor((now - d) / 1000);
    if(diff < 0) return '';
    if(diff < 60) return '방금 전';
    if(diff < 3600) return Math.floor(diff/60) + '분 전';
    if(diff < 86400) return Math.floor(diff/3600) + '시간 전';
    if(diff < 604800) return Math.floor(diff/86400) + '일 전';
    if(diff < 2592000) return Math.floor(diff/604800) + '주 전';
    return '';
  }
  document.querySelectorAll('.post-date[data-date]').forEach(function(el){
    var r = relTime(el.getAttribute('data-date'));
    if(r) el.insertAdjacentHTML('afterend', '<span class=\"post-date-relative\">' + r + '</span>');
  });
  document.querySelectorAll('time[datetime]').forEach(function(el){
    var r = relTime(el.getAttribute('datetime'));
    if(r) el.insertAdjacentHTML('afterend', '<span class=\"post-date-relative\">' + r + '</span>');
  });

  // ─── 인기 사이드바 로드 ───
  var popList = document.getElementById('popularList');
  function esc(s){return (s||'').replace(/[&<>\"']/g,function(c){return{'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',\"'\":'&#39;'}[c];});}
  function renderPopular(items){
    if(!popList) return;
    if(!items || !items.length){
      popList.innerHTML = '<li class=\"popular-empty\">아직 좋아요를 받은 글이 없어요.</li>';
      return;
    }
    popList.innerHTML = items.map(function(it, i){
      var thumb = it.thumbnail ? '<img src=\"'+esc(it.thumbnail)+'\" alt=\"\" loading=\"lazy\" onerror=\"this.style.display=\\'none\\'\">' : '<div class=\"popular-thumb-ph\"></div>';
      return '<li class=\"popular-item\">'
        + '<a href=\"'+esc(it.slug)+'.html\">'
        + '<span class=\"popular-rank\">'+(i+1)+'</span>'
        + '<div class=\"popular-thumb\">'+thumb+'</div>'
        + '<div class=\"popular-meta\">'
        +   '<div class=\"popular-item-title\">'+esc(it.title)+'</div>'
        +   '<div class=\"popular-item-likes\">👍 '+(it.likes||0)+'</div>'
        + '</div>'
        + '</a></li>';
    }).join('');
  }
  function loadPopular(){
    fetch('/api/popular?limit=10').then(function(r){return r.ok?r.json():[];}).then(renderPopular).catch(function(){});
  }
  loadPopular();

  // ─── 좋아요/싫어요 ───
  var reactEl = document.querySelector('.post-reactions');
  if(reactEl){
    var slug = reactEl.getAttribute('data-slug');
    var storeKey = 'vote:' + slug;
    function setCount(k,v){
      var el = reactEl.querySelector('[data-count=\"'+k+'\"]');
      if(el) el.textContent = v;
    }
    function markActive(){
      var s = localStorage.getItem(storeKey);
      reactEl.querySelector('.like-btn').classList.toggle('active', s==='like');
      reactEl.querySelector('.dislike-btn').classList.toggle('active', s==='dislike');
    }
    function loadStats(){
      fetch('/api/stats?slug=' + encodeURIComponent(slug))
        .then(function(r){return r.ok?r.json():{likes:0,dislikes:0};})
        .then(function(d){ setCount('likes', d.likes||0); setCount('dislikes', d.dislikes||0); })
        .catch(function(){});
    }
    function vote(action){
      var payload = {
        slug: slug,
        action: action,
        title: reactEl.getAttribute('data-title'),
        thumbnail: reactEl.getAttribute('data-thumbnail'),
        category: reactEl.getAttribute('data-category')
      };
      fetch('/api/vote', {
        method: 'POST',
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify(payload)
      }).then(function(r){return r.ok?r.json():null;}).then(function(d){
        if(!d) return;
        setCount('likes', d.likes||0);
        setCount('dislikes', d.dislikes||0);
        loadPopular();
      }).catch(function(){});
    }
    reactEl.querySelectorAll('.reaction-btn').forEach(function(btn){
      btn.addEventListener('click', function(){
        var action = btn.getAttribute('data-action');
        var cur = localStorage.getItem(storeKey);
        if(cur === action){
          vote(action === 'like' ? 'unlike' : 'undislike');
          localStorage.removeItem(storeKey);
        } else {
          if(cur === 'like') vote('unlike');
          if(cur === 'dislike') vote('undislike');
          vote(action);
          localStorage.setItem(storeKey, action);
        }
        markActive();
      });
    });
    markActive();
    loadStats();
  }
})();
</script>"""


def html_footer():
    return f"""
  <footer class="site-footer">
    <div class="container">
      <p>&copy; {datetime.now().year} {SITE_TITLE}</p>
    </div>
  </footer>
{relative_time_script()}
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
    tags_footer = "".join(f'<a class="tag">#{t} </a>' for t in tags) if tags else ""

    # 카테고리 slug 찾기
    cat_slug = CATEGORY_TO_SLUG.get(category, "all")

    slug = meta.get("slug", "").strip('"') or title
    thumb_for_data = thumbnail or ""

    hero_src = thumbnail or placeholder_svg(category, 720, 360)
    hero_img = img_with_fallback(hero_src, title, category)
    hero = f"""
      <div class="post-hero">
        {hero_img}
      </div>"""

    reactions = f"""
      <div class="post-reactions"
           data-slug="{slug}"
           data-title="{title}"
           data-thumbnail="{thumb_for_data}"
           data-category="{category}">
        <button type="button" class="reaction-btn like-btn" data-action="like" aria-label="좋아요">
          <span class="reaction-icon">👍</span>
          <span class="reaction-label">좋아요</span>
          <span class="reaction-count" data-count="likes">0</span>
        </button>
        <button type="button" class="reaction-btn dislike-btn" data-action="dislike" aria-label="싫어요">
          <span class="reaction-icon">👎</span>
          <span class="reaction-label">싫어요</span>
          <span class="reaction-count" data-count="dislikes">0</span>
        </button>
      </div>"""

    return f"""{html_head(f"{title} — {SITE_TITLE}", title, thumbnail, True)}
{html_header(cat_slug)}
  <main class="container">
    <article class="post-single">
      <header class="post-header">
        <span class="post-category">{category}</span>
        <h1>{title}</h1>
        <div class="post-meta">
          <div class="post-date-group">
            <time datetime="{date_str}">{date_str}</time>
          </div>
          <div class="post-tags">{tags_html}</div>
        </div>
      </header>
      {hero}
      <div class="post-content">
        {body_html}
      </div>
      {reactions}
      <footer class="post-footer">
        <div class="post-tags-footer">{tags_footer}</div>
      </footer>
    </article>
  </main>
{html_footer()}"""


# 카테고리별 플레이스홀더 색상
CATEGORY_COLORS = {
    "정치": ("#1a1a2e", "#16213e", "정치"),
    "사회": ("#2d3436", "#636e72", "사회"),
    "경제": ("#0a3d62", "#3c6382", "경제"),
    "연예": ("#6c5ce7", "#a29bfe", "연예"),
    "생활": ("#00b894", "#55efc4", "생활"),
    "IT": ("#0984e3", "#74b9ff", "IT"),
    "스포츠": ("#d63031", "#ff7675", "스포츠"),
    "패션": ("#e17055", "#fab1a0", "패션"),
    "사건사고": ("#2d3436", "#b2bec3", "사건사고"),
}


def placeholder_svg(category, width=400, height=220):
    """카테고리별 SVG 플레이스홀더 생성 (data URI)"""
    colors = CATEGORY_COLORS.get(category, ("#6c757d", "#adb5bd", category or "뉴스"))
    c1, c2, label = colors
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}">
<defs><linearGradient id="g" x1="0%" y1="0%" x2="100%" y2="100%">
<stop offset="0%" style="stop-color:{c1}"/><stop offset="100%" style="stop-color:{c2}"/>
</linearGradient></defs>
<rect width="{width}" height="{height}" fill="url(#g)" rx="12"/>
<text x="50%" y="50%" font-family="sans-serif" font-size="28" font-weight="600"
fill="rgba(255,255,255,0.85)" text-anchor="middle" dy=".35em">{label}</text></svg>'''
    import base64
    b64 = base64.b64encode(svg.encode()).decode()
    return f"data:image/svg+xml;base64,{b64}"


def img_with_fallback(src, alt, category, loading="lazy", extra_class=""):
    """이미지 태그 + onerror 폴백"""
    fallback = placeholder_svg(category)
    cls = f' class="{extra_class}"' if extra_class else ''
    return f'<img src="{src}" alt="{alt}" loading="{loading}"{cls} onerror="this.onerror=null;this.src=\'{fallback}\'">'


def render_post_cards(posts, show_featured=True):
    """게시물 카드 HTML 생성"""
    cards = ""
    for i, p in enumerate(posts):
        date_val = p['date'][:10]
        date_iso = p.get('date_iso', date_val)
        cat = p.get('category', '')
        thumb_src = p.get("thumbnail") or placeholder_svg(cat)

        if i == 0 and show_featured:
            img_tag = img_with_fallback(thumb_src, p["title"], cat)
            cards += f"""
    <article class="post-featured">
      <div class="post-meta-top">
        <span class="post-category">{cat}</span>
        <span class="post-date" data-date="{date_iso}">{date_val}</span>
      </div>
      <div class="featured-image">{img_tag}</div>
      <h2><a href="{p['slug']}.html">{p['title']}</a></h2>
      <p class="post-summary">{p.get('summary', '')}</p>
    </article>"""
        else:
            img_tag = img_with_fallback(thumb_src, p["title"], cat)
            cards += f"""
    <article class="post-card">
      <div class="post-thumb">
        <a href="{p['slug']}.html">{img_tag}</a>
      </div>
      <div class="post-info">
        <div class="post-meta-top">
          <span class="post-category">{cat}</span>
          <span class="post-date" data-date="{date_iso}">{date_val}</span>
        </div>
        <h2><a href="{p['slug']}.html">{p['title']}</a></h2>
        <p class="post-summary">{p.get('summary', '')}</p>
      </div>
    </article>"""
    return cards


def pagination_html(current_page, total_pages, prefix="index"):
    """페이지네이션 네비게이션 HTML 생성"""
    if total_pages <= 1:
        return ""

    def page_href(p):
        if prefix == "index":
            return "index.html" if p == 1 else f"page-{p}.html"
        else:
            return f"{prefix}.html" if p == 1 else f"{prefix}-page-{p}.html"

    items = ""

    # 이전 버튼
    if current_page > 1:
        items += f'<li><a href="{page_href(current_page - 1)}">&laquo; 이전</a></li>\n'

    # 페이지 번호 (최대 7개 표시)
    start = max(1, current_page - 3)
    end = min(total_pages, start + 6)
    start = max(1, end - 6)

    if start > 1:
        items += f'<li><a href="{page_href(1)}">1</a></li>\n'
        if start > 2:
            items += '<li><span class="page-dots">…</span></li>\n'

    for p in range(start, end + 1):
        if p == current_page:
            items += f'<li><span class="active">{p}</span></li>\n'
        else:
            items += f'<li><a href="{page_href(p)}">{p}</a></li>\n'

    if end < total_pages:
        if end < total_pages - 1:
            items += '<li><span class="page-dots">…</span></li>\n'
        items += f'<li><a href="{page_href(total_pages)}">{total_pages}</a></li>\n'

    # 다음 버튼
    if current_page < total_pages:
        items += f'<li><a href="{page_href(current_page + 1)}">다음 &raquo;</a></li>\n'

    return f"""
    <nav class="pagination-nav">
      <ul class="pagination">
        {items}
      </ul>
    </nav>"""


def render_index(posts, page=1, total_pages=1):
    """메인 페이지 (페이지네이션)"""
    start = (page - 1) * POSTS_PER_PAGE
    end = start + POSTS_PER_PAGE
    display_posts = posts[start:end]
    show_featured = (page == 1)
    cards = render_post_cards(display_posts, show_featured=show_featured)
    pager = pagination_html(page, total_pages, prefix="index")

    subtitle = "최신 뉴스를 빠르고 정확하게 전달합니다."
    if page > 1:
        subtitle = f"전체 {len(posts)}개 게시물 — {page}/{total_pages} 페이지"

    return f"""{html_head(SITE_TITLE, "최신 뉴스를 빠르고 정확하게")}
{html_header("all")}
  <main class="container">
    <div class="post-list">
      <h1>오늘의 뉴스</h1>
      <p class="post-list-subtitle">{subtitle}</p>
      {cards}
      {pager}
    </div>
  </main>
{html_footer()}"""


def render_category_page(cat_slug, cat_name, all_posts, page=1, total_pages=1):
    """카테고리별 게시판 페이지 (페이지네이션)"""
    start = (page - 1) * POSTS_PER_PAGE
    end = start + POSTS_PER_PAGE
    display_posts = all_posts[start:end]
    show_featured = (page == 1)
    cards = render_post_cards(display_posts, show_featured=show_featured)
    pager = pagination_html(page, total_pages, prefix=f"category-{cat_slug}")
    count = len(all_posts)

    subtitle = f"{cat_name} 관련 뉴스 {count}건"
    if page > 1:
        subtitle = f"{cat_name} 관련 뉴스 {count}건 — {page}/{total_pages} 페이지"

    return f"""{html_head(f"{cat_name} — {SITE_TITLE}", f"{cat_name} 카테고리 뉴스")}
{html_header(cat_slug)}
  <main class="container">
    <div class="post-list">
      <h1>{cat_name}</h1>
      <p class="post-list-subtitle">{subtitle}</p>
      {cards}
      {pager}
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
        slug = nfc(meta.get("slug", md_file.stem).strip('"'))
        meta["slug"] = slug  # 정규화된 값으로 갱신 (render_post가 재사용)

        # 상세 페이지 히어로 이미지와 본문 첫 이미지 중복 제거
        thumb_url = meta.get("thumbnail", "").strip().strip('"').strip("'")
        if thumb_url:
            # 1) 정확히 같은 src를 가진 figure 제거
            body_html = re.sub(
                r'<figure[^>]*>\s*<img[^>]*src="' + re.escape(thumb_url) + r'"[^>]*>\s*</figure>',
                '', body_html, count=1
            )
            # 2) 폴백: 본문 맨 앞 figure가 동일 URL이면 제거
            first_img = re.search(r'<figure[^>]*>\s*<img[^>]*src="([^"]+)"', body_html)
            if first_img and first_img.group(1) == thumb_url:
                body_html = re.sub(r'<figure[^>]*>\s*<img[^>]*>\s*</figure>', '', body_html, count=1)

        summary = re.sub(r"<[^>]+>", "", body_html)[:180] + "..."

        # 카테고리 정규화
        raw_cat = meta.get("category", "").strip()
        cat_slug = CATEGORY_TO_SLUG.get(raw_cat, "")
        display_cat = raw_cat if raw_cat else "일반"

        page_html = render_post(meta, body_html)
        out_path = PUBLIC_DIR / f"{slug}.html"
        out_path.write_text(page_html, encoding="utf-8")

        # md 파일 생성 시간 (macOS: st_birthtime, Linux: st_mtime fallback)
        stat = md_file.stat()
        try:
            file_ctime = stat.st_birthtime
        except AttributeError:
            file_ctime = stat.st_mtime

        # ISO 포맷 타임스탬프 (상대시간 계산용)
        ctime_iso = datetime.fromtimestamp(file_ctime).strftime("%Y-%m-%dT%H:%M:%S")

        posts.append({
            "title": meta.get("title", ""),
            "date": meta.get("date", ""),
            "date_iso": ctime_iso,
            "category": display_cat,
            "cat_slug": cat_slug,
            "thumbnail": meta.get("thumbnail", ""),
            "slug": slug,
            "summary": summary,
            "file_ctime": file_ctime,
        })

    # md 파일 생성 시간 기준 역순 정렬 (최신 파일이 위)
    # frontmatter date 기준 역순 정렬 (최신 날짜 우선), 같은 날짜면 파일 생성 시간 역순
    posts.sort(key=lambda x: (x["date"][:10], x["file_ctime"]), reverse=True)

    # ── 메인 페이지 (페이지네이션) ──
    import math
    total_main_pages = max(1, math.ceil(len(posts) / POSTS_PER_PAGE))
    for page_num in range(1, total_main_pages + 1):
        page_html = render_index(posts, page=page_num, total_pages=total_main_pages)
        if page_num == 1:
            (PUBLIC_DIR / "index.html").write_text(page_html, encoding="utf-8")
        else:
            (PUBLIC_DIR / f"page-{page_num}.html").write_text(page_html, encoding="utf-8")
    print(f"  메인 페이지: {total_main_pages}페이지 (전체 {len(posts)}개, 페이지당 {POSTS_PER_PAGE}개)")

    # ── 카테고리별 게시판 페이지 (페이지네이션) ──
    cat_posts = defaultdict(list)
    for p in posts:
        if p["cat_slug"]:
            cat_posts[p["cat_slug"]].append(p)

    for cat_slug, cat_name in CATEGORIES.items():
        if cat_slug == "all":
            continue
        cat_page_posts = cat_posts.get(cat_slug, [])
        total_cat_pages = max(1, math.ceil(len(cat_page_posts) / POSTS_PER_PAGE))
        for page_num in range(1, total_cat_pages + 1):
            cat_html = render_category_page(cat_slug, cat_name, cat_page_posts, page=page_num, total_pages=total_cat_pages)
            if page_num == 1:
                out_path = PUBLIC_DIR / f"category-{cat_slug}.html"
            else:
                out_path = PUBLIC_DIR / f"category-{cat_slug}-page-{page_num}.html"
            out_path.write_text(cat_html, encoding="utf-8")
        print(f"  카테고리 [{cat_name}]: {len(cat_page_posts)}개 ({total_cat_pages}페이지)")

    print(f"  완료!")


if __name__ == "__main__":
    build()
