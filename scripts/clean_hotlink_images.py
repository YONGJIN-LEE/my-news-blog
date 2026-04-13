#!/usr/bin/env python3
"""
외부 핫링크 이미지 정리 도구.

다음 두 가지 문제를 해결한다.
1) 저작권: 언론사·포털 CDN에서 이미지를 직접 링크하는 행위를 제거
2) 링크 수명: 핫링크는 언제든 404가 될 수 있음

전략:
  - 썸네일(front matter thumbnail): 외부 URL → 빈 값으로 제거.
    (빌드 시 build_html.py의 placeholder_svg가 카테고리별 SVG로 대체)
  - 본문 이미지 ![alt](http...): 라인 자체 제거하고, 해당 자리에
    "> 이미지 출처: [호스트](URL)" 블록쿼트를 남겨 독자에게 고지.
    (완전히 지우면 맥락이 사라지고, 링크로 남기면 저작권은 해결됨)

사용법:
  python3 scripts/clean_hotlink_images.py                       # 드라이런 (파일 수정 없음)
  python3 scripts/clean_hotlink_images.py --limit 5             # 샘플 5개만 미리보기
  python3 scripts/clean_hotlink_images.py --apply               # 실제 수정 (백업 자동 생성)
  python3 scripts/clean_hotlink_images.py --apply --mode remove # 본문 이미지 완전 삭제 (블록쿼트도 없이)

옵션:
  --mode quote   (기본) 본문 이미지를 "이미지 출처" 블록쿼트로 치환
  --mode remove  본문 이미지 라인 완전 제거
  --allow-hosts host1,host2   이 도메인은 건드리지 않음 (자체 CDN 등)
"""
import argparse
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

SCRIPT_DIR = Path(__file__).parent.resolve()
BLOG_DIR = SCRIPT_DIR.parent
CONTENT_DIR = BLOG_DIR / "content" / "posts"

# 건드리지 않을 도메인 (자체 자산, 무료 라이선스)
DEFAULT_ALLOW = {
    "images.unsplash.com",
    "picsum.photos",  # 자체 플레이스홀더 용도
}

THUMB_RE = re.compile(r'^(thumbnail:\s*)["\']?(https?://[^"\'\s]+)["\']?\s*$', re.M)
BODY_IMG_RE = re.compile(r'^!\[([^\]]*)\]\((https?://[^)\s]+)\)[ \t]*$', re.M)


def host_of(url: str) -> str:
    return (urlparse(url).hostname or "").lower()


def process_text(text: str, mode: str, allow: set) -> tuple[str, int, int]:
    """Returns (new_text, thumb_changes, body_changes)."""
    thumb_changes = 0
    body_changes = 0

    # 썸네일 제거
    def thumb_sub(m):
        nonlocal thumb_changes
        url = m.group(2)
        if host_of(url) in allow:
            return m.group(0)
        thumb_changes += 1
        return 'thumbnail: ""'

    text = THUMB_RE.sub(thumb_sub, text)

    # 본문 이미지 치환
    def body_sub(m):
        nonlocal body_changes
        url = m.group(2)
        host = host_of(url)
        if host in allow:
            return m.group(0)
        body_changes += 1
        if mode == "remove":
            return ""
        # quote mode: 출처 고지
        return f"> 이미지 출처: [{host}]({url})"

    text = BODY_IMG_RE.sub(body_sub, text)

    return text, thumb_changes, body_changes


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="실제 파일 수정 (기본은 드라이런)")
    ap.add_argument("--mode", choices=["quote", "remove"], default="quote")
    ap.add_argument("--limit", type=int, default=0, help="처리할 파일 수 제한 (0=전체)")
    ap.add_argument("--allow-hosts", default="", help="콤마 구분 허용 도메인 추가")
    args = ap.parse_args()

    allow = set(DEFAULT_ALLOW)
    if args.allow_hosts:
        allow |= {h.strip().lower() for h in args.allow_hosts.split(",") if h.strip()}

    md_files = sorted(CONTENT_DIR.glob("*.md"))
    if args.limit:
        md_files = md_files[: args.limit]

    if args.apply:
        backup_dir = BLOG_DIR / f"content_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        shutil.copytree(CONTENT_DIR, backup_dir / "posts")
        print(f"백업 생성: {backup_dir}")

    total_thumb = 0
    total_body = 0
    changed_files = 0
    samples_shown = 0

    for p in md_files:
        text = p.read_text(encoding="utf-8")
        new_text, tc, bc = process_text(text, args.mode, allow)
        if tc == 0 and bc == 0:
            continue
        changed_files += 1
        total_thumb += tc
        total_body += bc

        if samples_shown < 3 and not args.apply:
            import difflib
            print(f"\n=== {p.name} (thumb={tc}, body={bc}) ===")
            diff = difflib.unified_diff(
                text.splitlines(), new_text.splitlines(),
                lineterm="", n=1,
            )
            for line in diff:
                if line.startswith(("---", "+++", "@@")):
                    continue
                print(line)
            samples_shown += 1

        if args.apply:
            p.write_text(new_text, encoding="utf-8")

    print(f"\n--- 요약 ---")
    print(f"처리 파일: {len(md_files)}개 중 변경 {changed_files}개")
    print(f"썸네일 제거: {total_thumb}건")
    print(f"본문 이미지 {'치환' if args.mode == 'quote' else '제거'}: {total_body}건")
    if not args.apply:
        print("\n(드라이런 — 실제 수정하려면 --apply 추가)")


if __name__ == "__main__":
    sys.exit(main() or 0)
