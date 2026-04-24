#!/usr/bin/env python3
"""
drafts/published → 개인 블로그 자동 포스팅 스크립트

사용법:
  python3 publish_to_blog.py [시간대] [--category general|it|sports|fashion]
  python3 publish_to_blog.py --bulk          # drafts+published 전체 일괄 변환
  python3 publish_to_blog.py --bulk --with-images  # 이미지 포함 일괄 변환

기능:
  1. md 파일 → Hugo 포스트(front matter 포함) 변환
  2. 네이버 이미지 검색 API로 관련 뉴스 이미지 자동 삽입 (기존 blogger_post.py 로직)
  3. Hugo 빌드 또는 Python 빌더로 HTML 생성
  4. 일반 모드: 완료 후 published/ 이동 / bulk 모드: 이동 없이 변환만
"""

import os
import sys
import re
import json
import shutil
import subprocess
import hashlib
import unicodedata
from datetime import datetime, date
from pathlib import Path
from urllib.parse import urlparse

# ─── 경로 설정 ─────────────────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).parent.resolve()
BLOG_DIR = SCRIPT_DIR.parent
PROJECT_DIR = BLOG_DIR.parent
CONTENT_DIR = BLOG_DIR / "content" / "posts"
PUBLIC_DIR = BLOG_DIR / "public"

DRAFTS_DIR = PROJECT_DIR / "drafts"
PUBLISHED_DIR = PROJECT_DIR / "published"
CREDENTIALS_FILE = PROJECT_DIR / ".credentials.json"
LOG_FILE = PROJECT_DIR / "logs" / "blog-posting.log"

# ─── 카테고리 / 시간대 ────────────────────────────────────────────────────────
NON_GENERAL_TAGS = {"[IT]", "[Sports]", "[패션]"}
CATEGORY_TAGS = {"general": None, "it": "[IT]", "sports": "[Sports]", "fashion": "[패션]"}
CATEGORY_LABELS = {
    "[정치]": "정치", "[사회]": "사회", "[연예]": "연예",
    "[경제]": "경제", "[사건사고]": "사건사고", "[생활]": "생활",
    "[IT]": "IT", "[Sports]": "스포츠", "[패션]": "패션",
}
TIME_SLOTS = {"오전": "_오전_", "점심": "_점심_", "오후": "_오후_"}


def log(msg):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {msg}"
    print(line)
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")


# ─── 이모지 제거 ──────────────────────────────────────────────────────────────
EMOJI_RE = re.compile(
    "[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF"
    "\U0001F1E0-\U0001F1FF\U0001F900-\U0001F9FF\U0001FA00-\U0001FA6F"
    "\U0001FA70-\U0001FAFF\U00002702-\U000027B0\U0000FE00-\U0000FE0F"
    "\U00002600-\U000026FF\U0000200D\U00002B50\U00002B55"
    "\U000023E9-\U000023F3\U0000231A-\U0000231B\U00002934-\U00002935"
    "\U000025AA-\U000025FE\U00002194-\U000021AA\U0000203C\U00002049"
    "\U00002122\U00002139\U00002328\U000023CF\U000024C2"
    "\U000025FB-\U000025FE\U00002660-\U00002668\U0000267B-\U0000267F"
    "\U00002692-\U000026FF\U00002708-\U0000270D\U0000270F"
    "\U00002712\U00002714\U00002716\U0000271D\U00002721"
    "\U00002728\U00002733-\U00002734\U00002744\U00002747"
    "\U0000274C\U0000274E\U00002753-\U00002755\U00002757"
    "\U00002763-\U00002764\U00002795-\U00002797\U000027A1"
    "\U000027B0\U000027BF\U0000FE0F]+",
    flags=re.UNICODE,
)

def strip_emojis(text):
    return EMOJI_RE.sub("", text).strip()


# ─── 파일명 파싱 ──────────────────────────────────────────────────────────────
def parse_filename(filename):
    name = Path(filename).stem
    name = unicodedata.normalize("NFC", name)

    date_match = re.match(r"(\d{4}-\d{2}-\d{2})", name)
    post_date = date_match.group(1) if date_match else date.today().isoformat()

    time_slot = "오전"
    for slot in ["오전", "점심", "오후"]:
        if f"_{slot}_" in name or f"_{slot}" in name:
            time_slot = slot
            break

    category = ""
    cat_match = re.search(r"\[([^\]]+)\]", name)
    if cat_match:
        tag = f"[{cat_match.group(1)}]"
        category = CATEGORY_LABELS.get(tag, cat_match.group(1))

    keyword = name
    keyword = re.sub(r"\d{4}-\d{2}-\d{2}_?", "", keyword)
    keyword = re.sub(r"(오전|점심|오후)_?", "", keyword)
    keyword = re.sub(r"\[[^\]]+\]_?", "", keyword)
    keyword = re.sub(r"_\d{6}$", "", keyword)  # 시간 접미사 제거
    keyword = keyword.strip("_- ")

    return {"date": post_date, "time_slot": time_slot, "category": category, "keyword": keyword}


# ─── 마크다운 파싱 ────────────────────────────────────────────────────────────
def parse_markdown(content):
    title_match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
    title = strip_emojis(title_match.group(1).strip()) if title_match else ""

    tags = []
    # **태그:** 볼드 형식 또는 플레인 태그: 형식 둘 다 매칭
    tag_match = re.search(r"^\s*\*{0,2}태그\s*:\s*\*{0,2}\s*(.+)$", content, re.MULTILINE)
    if tag_match:
        tags = re.findall(r"#(\S+)", tag_match.group(1))

    return title, tags


def extract_search_keywords(title, tags, md_text=""):
    """제목·태그·소제목에서 이미지 검색 키워드 추출 (blogger_post.py 로직)"""
    stopwords = {"이", "가", "은", "는", "을", "를", "의", "에", "로", "으로",
                 "결국", "충격", "논란", "속보", "긴급", "발표", "확인", "총정리",
                 "완벽분석", "왜", "현재", "오늘", "위기", "전격", "비상"}
    short_title = re.split(r"[—\-!?]", title)[0].strip()

    tag_kw = [t for t in tags if t not in stopwords and len(t) > 1]

    section_subjects = []
    for m in re.finditer(r"^#{2,3}\s+(.+)$", md_text, re.MULTILINE):
        heading = strip_emojis(m.group(1).strip())
        generic = {"핵심 요약", "사건 개요", "이슈 개요", "상세 내용", "왜 주목받나",
                   "앞으로의 전망", "마무리", "댓글 유도", "사건/이슈 개요"}
        if any(g in heading for g in generic):
            continue
        if heading and len(heading) >= 4:
            section_subjects.append(heading)

    keywords = []
    nouns = [t for t in tag_kw[:5] if len(t) >= 2]
    if len(nouns) >= 2:
        keywords.append(f"{nouns[0]} {nouns[1]}")
    elif nouns:
        keywords.append(nouns[0])
    else:
        keywords.append(short_title)

    keywords.append(short_title)
    for subj in section_subjects[:3]:
        keywords.append(subj)
    keywords.append(f"{short_title} 뉴스")

    keywords = [k for k in keywords if len(k) >= 3]
    return keywords[:6]


# ─── 네이버 이미지 검색 (blogger_post.py 로직 이식) ───────────────────────────
def load_naver_credentials():
    if not CREDENTIALS_FILE.exists():
        return None, None
    with open(CREDENTIALS_FILE, "r") as f:
        creds = json.load(f)
    return creds.get("naver_client_id", ""), creds.get("naver_client_secret", "")


ALLOWED_IMAGE_DOMAINS = {
    "imgnews.naver.net", "mimgnews.naver.net", "imgnews.pstatic.net",
    "mimgnews.pstatic.net", "image.ytn.co.kr", "wimg.sedaily.com",
    "dimg.donga.com", "image.xportsnews.com", "thumb.mtstarnews.com",
    "img.seoul.co.kr", "img.sbs.co.kr", "image.news1.kr", "photo.jtbc.co.kr",
    "img.mbn.co.kr", "img.etoday.co.kr", "image.fnnews.com", "image.newsis.com",
    "img.tvreport.co.kr", "dispatch.cdnser.be", "img.hankyung.com",
    "img.khan.co.kr", "img.hani.co.kr", "image.chosun.com", "image.kmib.co.kr",
    "image.edaily.co.kr", "img3.yna.co.kr", "cphoto.asiae.co.kr",
    "thumb.mt.co.kr", "cdn.kmib.co.kr", "t1.daumcdn.net", "img1.daumcdn.net",
    "i.ytimg.com", "image.musinsa.com", "img.vogue.co.kr", "img.wkorea.com",
    "image.sports.media.naver.com", "img.sportalkorea.com",
    "pds.joongang.co.kr", "img.yonhapnews.co.kr", "img.osen.co.kr",
    "img.newspim.com", "img.tf.co.kr", "photo.isportskorea.com",
    "img.insight.co.kr", "interfootball.heraldcorp.com",
    "img.gqkorea.co.kr", "img.elle.co.kr", "img.allure.co.kr",
}


def is_allowed_domain(domain):
    for allowed in ALLOWED_IMAGE_DOMAINS:
        if domain == allowed or domain.endswith("." + allowed):
            return True
    return False


def fetch_naver_images(queries, client_id, client_secret, count=3):
    """네이버 이미지 검색 API — blogger_post.py와 동일 로직"""
    import requests
    if not client_id or not client_secret:
        return []
    images = []
    seen_urls = set()
    seen_domains = {}
    for query in queries:
        if len(images) >= count:
            break
        try:
            resp = requests.get(
                "https://openapi.naver.com/v1/search/image",
                params={"query": query, "display": 10, "sort": "sim"},
                headers={
                    "X-Naver-Client-Id": client_id,
                    "X-Naver-Client-Secret": client_secret,
                },
                timeout=10,
            )
            resp.raise_for_status()
            for item in resp.json().get("items", []):
                if len(images) >= count:
                    break
                img_url = item.get("link", "")
                if not img_url or img_url in seen_urls:
                    continue
                source_domain = urlparse(img_url).netloc.lower()
                if not is_allowed_domain(source_domain):
                    continue
                if seen_domains.get(source_domain, 0) >= 2:
                    continue
                seen_urls.add(img_url)
                seen_domains[source_domain] = seen_domains.get(source_domain, 0) + 1
                alt = item.get("title", query).replace("<b>", "").replace("</b>", "")
                images.append({"url": img_url, "alt": alt})
        except Exception as e:
            log(f"  이미지 검색 실패 ({query}): {e}")
    return images


# ─── Hugo 포스트 생성 ─────────────────────────────────────────────────────────
def create_hugo_post(md_path, with_images=True, naver_creds=(None, None)):
    filename = md_path.name
    meta = parse_filename(filename)

    content = md_path.read_text(encoding="utf-8")
    title, tags = parse_markdown(content)
    if not title:
        title = meta["keyword"]

    # ─── 기존 Hugo 포스트에 이미 네이버 이미지가 있으면 보존 ───
    existing_thumbnail = ""
    slug_check = re.sub(r"[^\w가-힣-]", "", meta["keyword"].replace(" ", "-"))
    slug_check = f"{meta['date']}-{slug_check}"
    existing_post = CONTENT_DIR / f"{slug_check}.md"
    if existing_post.exists():
        existing_content = existing_post.read_text(encoding="utf-8")
        thumb_m = re.search(r'^thumbnail:\s*"([^"]*)"', existing_content, re.MULTILINE)
        if thumb_m and thumb_m.group(1) and "picsum.photos" not in thumb_m.group(1):
            existing_thumbnail = thumb_m.group(1)

    # ─── 이미지 가져오기 (항상 시도) ───
    thumbnail = ""
    body_images = []

    # 1) 본문에 이미 삽입된 이미지 URL 추출
    inline_imgs = re.findall(r"!\[[^\]]*\]\(([^)]+)\)", content)

    # 2) 네이버 이미지 검색
    if naver_creds and naver_creds[0]:
        keywords = extract_search_keywords(title, tags, content)
        images = fetch_naver_images(keywords, naver_creds[0], naver_creds[1], count=5)
        if images:
            thumbnail = images[0]["url"]
            body_images = images

    # 3) 본문 인라인 이미지가 있으면 활용
    if not thumbnail and inline_imgs:
        thumbnail = inline_imgs[0]

    # 4) 기존 포스트의 thumbnail 보존
    if not thumbnail and existing_thumbnail:
        thumbnail = existing_thumbnail

    # 5) 최후 수단: fallback (picsum 대신 빈 문자열로 — 플레이스홀더 SVG 사용)
    if not thumbnail:
        thumbnail = ""

    # 마크다운 정리
    content = strip_emojis(content)
    content = re.sub(r"^(#{2,3}\s+)소제목\s*\d+\s*[:：]\s*", r"\1", content, flags=re.MULTILINE)
    content = re.sub(r"^#\s+.+\n+", "", content, count=1)
    # **태그:** 볼드 형식 또는 플레인 태그: 형식 둘 다 제거
    content = re.sub(r"^\s*\*{0,2}태그\s*:\s*\*{0,2}\s*.+$", "", content, flags=re.MULTILINE)
    content = re.sub(r"\n---\n", "\n", content)

    # 이미지 마크다운 삽입 (최소 2장)
    if body_images:
        # 첫 이미지: 본문 상단
        first_img = f'![{body_images[0]["alt"]}]({body_images[0]["url"]})'
        content = first_img + "\n\n" + content
        # 두 번째 이미지: 본문 중간 (첫 ## 소제목 뒤)
        if len(body_images) >= 2:
            second_img = f'\n![{body_images[1]["alt"]}]({body_images[1]["url"]})\n'
            h2_match = re.search(r"(^##\s+.+\n)", content, re.MULTILINE)
            if h2_match:
                pos = h2_match.end()
                content = content[:pos] + second_img + content[pos:]
            else:
                content = content + "\n" + second_img

    # slug 생성
    slug = re.sub(r"[^\w가-힣-]", "", meta["keyword"].replace(" ", "-"))
    slug = f"{meta['date']}-{slug}"

    time_str = "06:00" if meta["time_slot"] == "오전" else "14:00" if meta["time_slot"] == "점심" else "19:00"

    front_matter = f"""---
title: "{title}"
date: {meta['date']}T{time_str}:00+09:00
slug: "{slug}"
category: "{meta['category']}"
tags: {json.dumps(tags, ensure_ascii=False)}
thumbnail: "{thumbnail}"
description: "{title}"
draft: false
---
"""

    post_path = CONTENT_DIR / f"{slug}.md"
    CONTENT_DIR.mkdir(parents=True, exist_ok=True)
    post_path.write_text(front_matter + content.strip() + "\n", encoding="utf-8")

    return post_path, meta


# ─── 중복 검사 ────────────────────────────────────────────────────────────────
def get_existing_slugs():
    if not CONTENT_DIR.exists():
        return set()
    return {f.stem for f in CONTENT_DIR.glob("*.md")}


def make_slug(filename):
    meta = parse_filename(filename)
    slug = re.sub(r"[^\w가-힣-]", "", meta["keyword"].replace(" ", "-"))
    return f"{meta['date']}-{slug}"


# ─── 빌드 ────────────────────────────────────────────────────────────────────
def build():
    hugo_path = shutil.which("hugo")
    if hugo_path:
        log("Hugo 빌드...")
        result = subprocess.run(["hugo", "--minify"], cwd=str(BLOG_DIR), capture_output=True, text=True)
        if result.returncode == 0:
            log(f"Hugo 빌드 성공")
            return True

    builder = SCRIPT_DIR / "build_html.py"
    if builder.exists():
        log("Python 빌더...")
        result = subprocess.run([sys.executable, str(builder)], capture_output=True, text=True)
        if result.returncode == 0:
            log("Python 빌드 성공")
            return True
        else:
            log(f"빌드 실패: {result.stderr[:200]}")
    return False


# ─── 메인: 일반 모드 ─────────────────────────────────────────────────────────
def run_normal(time_slot, category):
    today = date.today().isoformat()
    log(f"═══ 블로그 포스팅: {today} {time_slot} [{category}] ═══")

    if not DRAFTS_DIR.exists():
        log("drafts 폴더 없음")
        return 0

    slot_key = TIME_SLOTS.get(time_slot, "")
    cat_tag = CATEGORY_TAGS.get(category)
    naver_creds = load_naver_credentials()
    existing = get_existing_slugs()

    candidates = []
    # drafts와 published 양쪽에서 파일 탐색 (Blogger가 먼저 실행되어 published로 이동했을 수 있음)
    for search_dir in [DRAFTS_DIR, PUBLISHED_DIR]:
        if not search_dir.exists():
            continue
        for f in sorted(search_dir.glob(f"{today}*.md")):
            name = unicodedata.normalize("NFC", f.name)
            if slot_key and slot_key not in name:
                if any(t in name for t in TIME_SLOTS.values()):
                    continue
                elif time_slot != "오전":
                    continue
            if category == "general":
                if any(tag in name for tag in NON_GENERAL_TAGS):
                    continue
            elif cat_tag and cat_tag not in name:
                continue

            slug = make_slug(f.name)
            if slug in existing:
                log(f"  중복 건너뜀: {f.name}")
                continue
            candidates.append(f)

    if not candidates:
        log("포스팅할 파일 없음")
        return 0

    log(f"대상 {len(candidates)}개")
    posted = []
    for md_file in candidates:
        try:
            log(f"  처리: {md_file.name}")
            post_path, _ = create_hugo_post(md_file, with_images=True, naver_creds=naver_creds)
            posted.append(md_file)
        except Exception as e:
            log(f"  오류: {e}")

    if posted:
        build()
        # 파일 이동은 하지 않음 — Blogger 포스팅 성공 시 blogger_post.py가 이동 처리

    log(f"═══ 완료: {len(posted)}개 ═══")
    return len(posted)


# ─── 메인: 일괄(bulk) 모드 ───────────────────────────────────────────────────
def run_bulk(with_images=False):
    log("═══ 전체 일괄 변환 시작 ═══")

    naver_creds = load_naver_credentials() if with_images else (None, None)
    existing = get_existing_slugs()

    # drafts + published 전체 수집
    all_files = []
    for d in [DRAFTS_DIR, PUBLISHED_DIR]:
        if d.exists():
            all_files.extend(d.glob("*.md"))

    log(f"총 파일: {len(all_files)}개")

    # 중복 제거 (같은 slug → 최신 파일 우선)
    slug_map = {}
    for f in all_files:
        slug = make_slug(f.name)
        if slug in slug_map:
            # 이미 있으면 수정시간 비교
            if f.stat().st_mtime > slug_map[slug].stat().st_mtime:
                slug_map[slug] = f
        else:
            slug_map[slug] = f

    # 이미 변환된 것 제외
    new_files = {slug: f for slug, f in slug_map.items() if slug not in existing}
    log(f"신규: {len(new_files)}개 (중복 제외, 기존 {len(existing)}개)")

    converted = 0
    total = len(new_files)
    for i, (slug, md_file) in enumerate(sorted(new_files.items()), 1):
        try:
            log(f"  [{i}/{total}] {md_file.name}")
            create_hugo_post(md_file, with_images=with_images, naver_creds=naver_creds)
            converted += 1
        except Exception as e:
            log(f"    오류: {e}")

    if converted:
        build()

    log(f"═══ 일괄 변환 완료: {converted}/{total}개 ═══")
    return converted


# ─── CLI ──────────────────────────────────────────────────────────────────────
def main():
    args = sys.argv[1:]

    if "--bulk" in args:
        with_images = "--with-images" in args
        run_bulk(with_images=with_images)
        return

    time_slot = None
    category = "general"
    for i, arg in enumerate(args):
        if arg in TIME_SLOTS:
            time_slot = arg
        elif arg == "--category" and i + 1 < len(args):
            category = args[i + 1].lower()

    if not time_slot:
        hour = datetime.now().hour
        time_slot = "오전" if hour < 12 else "점심" if hour < 17 else "오후"

    run_normal(time_slot, category)


if __name__ == "__main__":
    main()
