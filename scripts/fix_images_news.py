#!/usr/bin/env python3
"""
네이버 뉴스 검색 → 기사 OG 이미지 추출 → 게시물 썸네일/본문 이미지 추가

로직:
1. 게시물 제목에서 키워드 추출
2. 네이버 뉴스 검색 API로 관련 기사 찾기
3. 기사 URL에서 og:image 추출
4. 게시물 front matter thumbnail + 본문에 이미지 삽입
"""

import os
import re
import json
import time
import urllib.request
import urllib.parse
from pathlib import Path
from html.parser import HTMLParser

SCRIPT_DIR = Path(__file__).parent.resolve()
BLOG_DIR = SCRIPT_DIR.parent
CONTENT_DIR = BLOG_DIR / "content" / "posts"
CREDS_FILE = BLOG_DIR.parent / ".credentials.json"

# ─── API 인증 ───
with open(CREDS_FILE, encoding="utf-8") as f:
    creds = json.load(f)

NAVER_CLIENT_ID = creds.get("naver_client_id", "")
NAVER_CLIENT_SECRET = creds.get("naver_client_secret", "")


# ─── OG Image 파서 ───
class OGImageParser(HTMLParser):
    """HTML에서 og:image 메타 태그 추출"""
    def __init__(self):
        super().__init__()
        self.og_image = ""

    def handle_starttag(self, tag, attrs):
        if tag != "meta":
            return
        attrs_dict = dict(attrs)
        prop = attrs_dict.get("property", "")
        if prop == "og:image" and not self.og_image:
            self.og_image = attrs_dict.get("content", "")


# ─── 네이버 뉴스 검색 ───
def search_naver_news(query, display=5):
    """네이버 뉴스 검색 API → 기사 링크 리스트"""
    if not NAVER_CLIENT_ID:
        return []

    url = "https://openapi.naver.com/v1/search/news.json"
    params = urllib.parse.urlencode({
        "query": query,
        "display": display,
        "sort": "sim",
    })

    req = urllib.request.Request(f"{url}?{params}")
    req.add_header("X-Naver-Client-Id", NAVER_CLIENT_ID)
    req.add_header("X-Naver-Client-Secret", NAVER_CLIENT_SECRET)

    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("items", [])
    except Exception as e:
        print(f"    뉴스검색 에러: {e}")
        return []


def search_naver_images(query, display=5):
    """네이버 이미지 검색 API (폴백용)"""
    if not NAVER_CLIENT_ID:
        return []

    url = "https://openapi.naver.com/v1/search/image"
    params = urllib.parse.urlencode({
        "query": query,
        "display": display,
        "sort": "sim",
        "filter": "large",
    })

    req = urllib.request.Request(f"{url}?{params}")
    req.add_header("X-Naver-Client-Id", NAVER_CLIENT_ID)
    req.add_header("X-Naver-Client-Secret", NAVER_CLIENT_SECRET)

    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("items", [])
    except Exception as e:
        print(f"    이미지검색 에러: {e}")
        return []


# ─── 기사 페이지에서 OG 이미지 추출 ───
def extract_og_image(article_url):
    """기사 URL 접속 → og:image 메타 태그 추출"""
    try:
        req = urllib.request.Request(article_url)
        req.add_header("User-Agent", "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)")
        with urllib.request.urlopen(req, timeout=5) as resp:
            # head 부분만 읽기 (이미지 메타는 보통 앞부분에 있음)
            html = resp.read(30000).decode("utf-8", errors="ignore")

        parser = OGImageParser()
        parser.feed(html)
        return parser.og_image
    except Exception as e:
        return ""


# ─── 네이버 뉴스 URL → 원본 기사 URL 추출 ───
def get_original_link(naver_link):
    """네이버 뉴스 링크에서 originallink 가져오기"""
    # API가 이미 originallink를 제공하므로 그대로 사용
    return naver_link


# ─── 이미지 품질 검증 ───
BLOCKED_PATTERNS = [
    "logo", "icon", "banner", "ad_", "adimg",
    "1x1", "pixel", "spacer", "blank", "transparent",
    "facebook.com", "twitter.com", "kakaostory",
]

def is_valid_image(url):
    """유효한 뉴스 이미지인지 확인"""
    if not url or not url.startswith("http"):
        return False
    lower = url.lower()
    return not any(p in lower for p in BLOCKED_PATTERNS)


# ─── 키워드 추출 ───
def extract_search_query(title):
    """제목에서 검색 키워드 추출"""
    # 특수문자/괄호 등 제거
    clean = re.sub(r"[\[\](){}!?·…\"\''""''「」]", " ", title)
    clean = re.sub(r"\s+", " ", clean).strip()
    # 너무 길면 앞부분만
    words = clean.split()
    if len(words) > 6:
        return " ".join(words[:6])
    return clean


# ─── 메인 처리 ───
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
                    meta[key] = val
    return meta, body


def main():
    md_files = sorted(CONTENT_DIR.glob("*.md"))
    print(f"전체 포스트: {len(md_files)}개\n")

    fixed = 0
    skipped = 0
    failed = 0

    for md_file in md_files:
        content = md_file.read_text(encoding="utf-8")
        meta, body = parse_front_matter(content)

        thumb = meta.get("thumbnail", "")
        has_valid_thumb = bool(thumb) and "picsum" not in thumb
        has_body_image = bool(re.search(r"!\[", body))

        # 이미 이미지 완비 → 스킵
        if has_valid_thumb and has_body_image:
            skipped += 1
            continue

        title = meta.get("title", md_file.stem)
        query = extract_search_query(title)

        if not query:
            continue

        print(f"  [{fixed+failed+1}] {title[:45]}...", end=" ", flush=True)

        # 포스트당 최대 3개 이미지 수집 (중복 제거)
        TARGET_IMAGES = 3
        img_urls = []

        def add_image(url):
            if url and is_valid_image(url) and url not in img_urls:
                img_urls.append(url)
                return True
            return False

        # ── 방법 1: 네이버 뉴스 검색 → 여러 기사의 OG 이미지 수집 ──
        news_items = search_naver_news(query, display=8)
        for item in news_items:
            if len(img_urls) >= TARGET_IMAGES:
                break
            article_url = item.get("originallink") or item.get("link", "")
            if not article_url:
                continue
            og = extract_og_image(article_url)
            add_image(og)
            time.sleep(0.05)

        # ── 방법 2: 네이버 이미지 검색 (부족분 채우기) ──
        if len(img_urls) < TARGET_IMAGES:
            img_items = search_naver_images(query, display=8)
            for item in img_items:
                if len(img_urls) >= TARGET_IMAGES:
                    break
                add_image(item.get("link", ""))

        # ── 방법 3: 키워드 줄여서 재시도 (여전히 부족하면) ──
        if len(img_urls) < TARGET_IMAGES:
            short_query = " ".join(query.split()[:3])
            if short_query and short_query != query:
                news_items2 = search_naver_news(short_query, display=5)
                for item in news_items2:
                    if len(img_urls) >= TARGET_IMAGES:
                        break
                    article_url = item.get("originallink") or item.get("link", "")
                    if not article_url:
                        continue
                    og = extract_og_image(article_url)
                    add_image(og)
                    time.sleep(0.05)

        if not img_urls:
            print("✗ 이미지 없음")
            failed += 1
            continue

        # ── 적용 ──
        new_content = content
        thumb_url = img_urls[0]

        # 1) 썸네일 업데이트 (첫 번째 이미지)
        if not has_valid_thumb:
            new_content = re.sub(
                r'thumbnail:\s*"[^"]*"',
                f'thumbnail: "{thumb_url}"',
                new_content,
            )

        # 2) 본문 이미지 삽입 — 여러 섹션에 분산
        if not has_body_image:
            sections = new_content.split("\n## ")
            # 본문에 넣을 이미지: 썸네일 포함 전부 (build_html.py가 중복 제거)
            body_imgs = img_urls[:TARGET_IMAGES]

            if len(sections) >= 2 and body_imgs:
                # 각 이미지를 서로 다른 섹션에 배치 (섹션 1, 2, 3 ... 순서로)
                max_insert = min(len(body_imgs), len(sections) - 1)
                for i in range(max_insert):
                    sec_idx = i + 1  # 섹션 1부터
                    img = body_imgs[i]
                    alt = f"{title}" if i == 0 else f"{title} 관련 이미지 {i+1}"
                    sections[sec_idx] = sections[sec_idx] + f"\n\n![{alt}]({img})\n"
                new_content = "\n## ".join(sections)

        md_file.write_text(new_content, encoding="utf-8")
        fixed += 1
        print(f"✓ 완료 ({len(img_urls)}장)")

        # API 속도 제한 방지
        time.sleep(0.2)

    print(f"\n{'='*50}")
    print(f"결과: {fixed}개 수정 | {failed}개 실패 | {skipped}개 스킵")
    print(f"{'='*50}")


if __name__ == "__main__":
    main()
