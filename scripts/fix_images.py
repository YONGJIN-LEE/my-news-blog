#!/usr/bin/env python3
"""
본문에 이미지가 없는 게시물에 Naver Image Search API로 이미지 추가
+ picsum placeholder 썸네일을 실제 이미지로 교체
"""

import os
import re
import json
import time
import urllib.request
import urllib.parse
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent.resolve()
BLOG_DIR = SCRIPT_DIR.parent
CONTENT_DIR = BLOG_DIR / "content" / "posts"
CREDS_FILE = BLOG_DIR.parent / ".credentials.json"

# Naver API
with open(CREDS_FILE, encoding="utf-8") as f:
    creds = json.load(f)

NAVER_CLIENT_ID = creds.get("naver_client_id", "")
NAVER_CLIENT_SECRET = creds.get("naver_client_secret", "")

# 허용 이미지 도메인 (뉴스/미디어)
ALLOWED_DOMAINS = {
    "imgnews.pstatic.net", "mimgnews.pstatic.net", "image.news.livedoor.com",
    "cdn.news.media", "img.hani.co.kr", "image.kmib.co.kr",
    "dimg.donga.com", "image.chosun.com", "img.sbs.co.kr",
    "img.khan.co.kr", "image.busan.com", "img.insight.co.kr",
    "cdn.mhns.co.kr", "img.etnews.com", "image.zdnet.co.kr",
    "thumb.mt.co.kr", "img.wowtv.co.kr", "newsimg.sedaily.com",
    "img.etoday.co.kr", "cdn.newsen.com", "img.sportsworldi.com",
    "image.newsis.com", "img.asiatoday.co.kr", "cdnimage.dailian.co.kr",
    "img.yonhapnews.co.kr", "img.mk.co.kr", "image.fnnews.com",
    "img.hankyung.com", "img.tvreport.co.kr", "cdn.stardailynews.co.kr",
    "image.xportsnews.com", "img.enews24.cjenm.skcd.com",
    "cdn.newsculture.press", "img.tf.co.kr", "img.gqkorea.co.kr",
    "img.vogue.co.kr", "img.wkorea.com", "image.jtbcplus.kr",
    "img.allurekorea.com", "pds.joongang.co.kr", "flexible.img.hani.co.kr",
    "img.seoul.co.kr", "image.edaily.co.kr", "img.heraldcorp.com",
}


def fetch_naver_images(query, display=5):
    """Naver 이미지 검색 API 호출"""
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
        print(f"    API 에러: {e}")
        return []


def pick_best_image(items, keyword=""):
    """허용 도메인 우선, 없으면 아무거나"""
    # 1차: 허용 도메인에서 찾기
    for item in items:
        link = item.get("link", "")
        try:
            domain = urllib.parse.urlparse(link).hostname
            if domain in ALLOWED_DOMAINS:
                return link
        except:
            pass

    # 2차: 아무 이미지나 (https만)
    for item in items:
        link = item.get("link", "")
        if link.startswith("https://"):
            return link

    return ""


def extract_keywords(meta, body):
    """제목, 태그에서 검색 키워드 추출"""
    title = meta.get("title", "")
    tags = meta.get("tags", [])
    if isinstance(tags, str):
        try:
            tags = json.loads(tags)
        except:
            tags = []

    # 제목에서 핵심 키워드 (첫 15자 정도)
    keyword = title[:20] if title else ""

    # 태그가 있으면 첫 2개 추가
    if tags and isinstance(tags, list):
        tag_str = " ".join(str(t).replace("#", "") for t in tags[:2])
        keyword = f"{keyword} {tag_str}"

    return keyword.strip()


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


def main():
    md_files = sorted(CONTENT_DIR.glob("*.md"))
    print(f"전체 포스트: {len(md_files)}개")

    fixed_count = 0
    error_count = 0

    for md_file in md_files:
        content = md_file.read_text(encoding="utf-8")
        meta, body = parse_front_matter(content)

        has_body_image = bool(re.search(r"!\[", body))
        has_placeholder = "picsum.photos" in content

        # 본문 이미지가 있고 placeholder도 아니면 스킵
        if has_body_image and not has_placeholder:
            continue

        title = meta.get("title", md_file.stem)
        keyword = extract_keywords(meta, body)

        if not keyword:
            continue

        print(f"  [{fixed_count+1}] {title[:40]}... → ", end="", flush=True)

        # Naver 이미지 검색
        items = fetch_naver_images(keyword)
        if not items:
            # 제목만으로 재시도
            items = fetch_naver_images(title[:15])

        if not items:
            print("이미지 없음")
            error_count += 1
            continue

        img_url = pick_best_image(items, keyword)
        if not img_url:
            print("적합한 이미지 없음")
            error_count += 1
            continue

        # 썸네일 교체 (picsum → 실제 이미지)
        new_content = content
        if has_placeholder:
            new_content = re.sub(
                r'thumbnail: "https://picsum\.photos/seed/\d+/1200/630"',
                f'thumbnail: "{img_url}"',
                new_content
            )

        # 본문에 이미지 없으면 첫 번째 ## 다음에 이미지 삽입
        if not has_body_image:
            # 두 번째 ## (첫 번째는 보통 핵심 요약) 뒤에 삽입
            sections = new_content.split("\n## ")
            if len(sections) >= 3:
                # 2번째 섹션 끝에 이미지 추가
                sections[1] = sections[1] + f"\n\n![{title}]({img_url})\n"
                new_content = "\n## ".join(sections)
            elif len(sections) >= 2:
                sections[1] = sections[1] + f"\n\n![{title}]({img_url})\n"
                new_content = "\n## ".join(sections)

        md_file.write_text(new_content, encoding="utf-8")
        fixed_count += 1
        print(f"완료")

        # API 속도 제한 방지
        time.sleep(0.15)

    print(f"\n완료: {fixed_count}개 수정, {error_count}개 이미지 없음")


if __name__ == "__main__":
    main()
