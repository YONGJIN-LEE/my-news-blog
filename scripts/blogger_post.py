#!/usr/bin/env python3
"""
content/posts/*.md → Google Blogger 자동 업로드

사용법:
  blogger_post.py 오전 --category general          # 단일 카테고리
  blogger_post.py 오전 --all                       # 전체 카테고리 (general→it→sports→fashion)
  blogger_post.py 오전 --all --dry-run             # 실제 호출 없이 시뮬레이션
  blogger_post.py --slug 2026-05-06-키워드          # 특정 슬러그 1건만
  blogger_post.py --retry-failed                   # 실패 큐 재시도

요구 자격증명 (/home/user/.credentials.json):
  {
    "blogger_client_id": "...",          # Google Cloud OAuth2 클라이언트 ID
    "blogger_client_secret": "...",      # 클라이언트 시크릿
    "blogger_refresh_token": "...",      # 리프레시 토큰 (offline access)
    "blogger_blog_id": "..."             # Blogger 블로그 ID (숫자)
  }

Rate-limit 정책 (워크플로우 표준):
  - 1건당 45초 간격 (--delay 로 조정)
  - 카테고리 간 120초 텀 (--category-gap 로 조정)
  - 일일 총합 40건 상한 (--daily-cap 로 조정)
  - 실패 시 지수 백오프 (60→120→240s, 최대 4회)
  - 차단 추정(403/429) 시 즉시 중단

업로드 추적:
  - logs/blogger-uploaded.log (성공) — 슬러그 단위 중복 방지
  - logs/blogger-failed.log (실패 큐) — --retry-failed 로 재시도

본 스크립트는 publish_to_blog.py 와 짝을 이뤄 동작:
  drafts/ → publish_to_blog.py → content/posts/ → blogger_post.py → Blogger
"""

import argparse
import json
import re
import sys
import time
import unicodedata
from datetime import datetime, date
from pathlib import Path

import requests

# ─── 경로 설정 ─────────────────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).parent.resolve()
BLOG_DIR = SCRIPT_DIR.parent
PROJECT_DIR = BLOG_DIR.parent
CONTENT_DIR = BLOG_DIR / "content" / "posts"
LOG_DIR = PROJECT_DIR / "logs"
CREDENTIALS_FILE = PROJECT_DIR / ".credentials.json"
UPLOADED_LOG = LOG_DIR / "blogger-uploaded.log"
FAILED_LOG = LOG_DIR / "blogger-failed.log"

# ─── 카테고리 / 시간대 ────────────────────────────────────────────────────────
TIME_SLOT_HOUR = {"오전": "T06:00:00", "점심": "T14:00:00", "오후": "T19:00:00"}
CATEGORIES = ["general", "it", "sports", "fashion"]
CATEGORY_LABEL_MATCH = {
    "general": {"정치", "사회", "연예", "경제", "사건사고", "생활"},
    "it":      {"IT"},
    "sports":  {"스포츠"},
    "fashion": {"패션"},
}

# ─── Rate-limit 기본값 ────────────────────────────────────────────────────────
DEFAULT_DELAY = 45             # 1건당 텀(초)
DEFAULT_CATEGORY_GAP = 120     # 카테고리 간 텀(초)
DEFAULT_DAILY_CAP = 40         # 일일 상한
BACKOFF_SCHEDULE = [60, 120, 240, 480]  # 지수 백오프 (최대 4회)


# ─── 로깅 ─────────────────────────────────────────────────────────────────────
def log(msg, level="INFO"):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] [{level}] {msg}"
    print(line)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    with open(LOG_DIR / "blogger-posting.log", "a", encoding="utf-8") as f:
        f.write(line + "\n")


# ─── 자격증명 ────────────────────────────────────────────────────────────────
def load_credentials():
    if not CREDENTIALS_FILE.exists():
        return None
    with open(CREDENTIALS_FILE, "r", encoding="utf-8") as f:
        creds = json.load(f)
    required = ["blogger_client_id", "blogger_client_secret",
                "blogger_refresh_token", "blogger_blog_id"]
    missing = [k for k in required if not creds.get(k)]
    if missing:
        log(f"자격증명 누락: {missing}", "ERROR")
        return None
    return creds


def refresh_access_token(client_id, client_secret, refresh_token):
    """Google OAuth2 refresh_token → access_token 교환"""
    resp = requests.post(
        "https://oauth2.googleapis.com/token",
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        },
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


# ─── Front matter 파싱 ────────────────────────────────────────────────────────
def parse_frontmatter(text):
    """Hugo front matter 파싱 (YAML 단순 파싱)"""
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.DOTALL)
    if not m:
        return None, text
    fm_text, body = m.group(1), m.group(2)
    fm = {}
    for line in fm_text.split("\n"):
        if ":" not in line:
            continue
        key, _, val = line.partition(":")
        key = key.strip()
        val = val.strip()
        if val.startswith('"') and val.endswith('"'):
            val = val[1:-1]
        elif val.startswith("[") and val.endswith("]"):
            try:
                val = json.loads(val)
            except Exception:
                val = []
        fm[key] = val
    return fm, body.strip()


# ─── Markdown → Blogger HTML 변환 ─────────────────────────────────────────────
def md_to_html(md_text):
    """Hugo 포스트의 단순 마크다운을 Blogger용 HTML로 변환

    지원: ## H2, ### H3, ![alt](url) 이미지, 일반 단락
    """
    html_blocks = []
    blocks = re.split(r"\n\s*\n", md_text.strip())
    for block in blocks:
        block = block.strip()
        if not block:
            continue
        # H2
        m = re.match(r"^##\s+(.+)$", block)
        if m:
            html_blocks.append(f"<h2>{escape_html(m.group(1).strip())}</h2>")
            continue
        # H3
        m = re.match(r"^###\s+(.+)$", block)
        if m:
            html_blocks.append(f"<h3>{escape_html(m.group(1).strip())}</h3>")
            continue
        # 이미지만 있는 단락
        m = re.match(r"^!\[([^\]]*)\]\(([^)]+)\)$", block)
        if m:
            alt = escape_html(m.group(1))
            url = m.group(2)
            html_blocks.append(
                f'<p><img src="{url}" alt="{alt}" '
                f'style="max-width:100%;height:auto;" /></p>'
            )
            continue
        # 일반 단락 (줄바꿈은 <br>, 인라인 이미지 변환)
        para = block
        # 인라인 이미지 변환
        para = re.sub(
            r"!\[([^\]]*)\]\(([^)]+)\)",
            lambda m: f'<img src="{m.group(2)}" alt="{escape_html(m.group(1))}" '
                      f'style="max-width:100%;height:auto;" />',
            para,
        )
        # 인라인 코드/볼드 단순 처리
        para = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", para)
        # 줄 단위 escape (이미지 태그는 보존)
        lines = para.split("\n")
        safe_lines = []
        for line in lines:
            # 이미 변환된 <img> 태그는 보존, 나머지는 escape
            if "<img " in line or "<strong>" in line:
                safe_lines.append(line)
            else:
                safe_lines.append(escape_html(line))
        html_blocks.append("<p>" + "<br />".join(safe_lines) + "</p>")
    return "\n".join(html_blocks)


def escape_html(s):
    return (s.replace("&", "&amp;").replace("<", "&lt;")
             .replace(">", "&gt;").replace('"', "&quot;"))


# ─── 포스트 픽업 ──────────────────────────────────────────────────────────────
def get_uploaded_slugs():
    if not UPLOADED_LOG.exists():
        return set()
    return {line.strip() for line in UPLOADED_LOG.read_text(encoding="utf-8").splitlines() if line.strip()}


def append_uploaded(slug, blogger_post_id):
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    with open(UPLOADED_LOG, "a", encoding="utf-8") as f:
        f.write(f"{slug}\t{blogger_post_id}\t{datetime.now().isoformat()}\n")


def append_failed(slug, error):
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    with open(FAILED_LOG, "a", encoding="utf-8") as f:
        f.write(f"{slug}\t{datetime.now().isoformat()}\t{error}\n")


def daily_count():
    """오늘 업로드한 건수"""
    if not UPLOADED_LOG.exists():
        return 0
    today_iso = date.today().isoformat()
    count = 0
    for line in UPLOADED_LOG.read_text(encoding="utf-8").splitlines():
        parts = line.split("\t")
        if len(parts) >= 3 and parts[2].startswith(today_iso):
            count += 1
    return count


def pick_posts(time_slot, category, target_date=None):
    """그 시간대·카테고리에 해당하는 미업로드 포스트 수집"""
    if not CONTENT_DIR.exists():
        return []
    hour_marker = TIME_SLOT_HOUR.get(time_slot, "")
    cat_labels = CATEGORY_LABEL_MATCH.get(category, set())
    uploaded = get_uploaded_slugs()
    target = target_date or date.today().isoformat()

    posts = []
    for f in sorted(CONTENT_DIR.glob(f"{target}-*.md")):
        slug = f.stem
        if slug in uploaded:
            continue
        text = f.read_text(encoding="utf-8")
        fm, body = parse_frontmatter(text)
        if not fm:
            continue
        # 시간대 필터
        if hour_marker and hour_marker not in fm.get("date", ""):
            continue
        # 카테고리 필터
        if fm.get("category") not in cat_labels:
            continue
        posts.append((f, fm, body))
    return posts


# ─── Blogger API ──────────────────────────────────────────────────────────────
def post_to_blogger(blog_id, access_token, title, html, labels):
    """Blogger API v3 POST"""
    url = f"https://www.googleapis.com/blogger/v3/blogs/{blog_id}/posts/"
    resp = requests.post(
        url,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        },
        json={
            "kind": "blogger#post",
            "title": title,
            "content": html,
            "labels": labels,
        },
        timeout=30,
    )
    return resp


def upload_one(post_file, fm, body, creds, access_token, dry_run=False):
    """포스트 1건 업로드 (지수 백오프 포함)"""
    slug = post_file.stem
    title = fm.get("title", slug)
    labels = fm.get("tags", [])
    if isinstance(labels, str):
        labels = [labels]
    if fm.get("category"):
        labels = [fm["category"]] + [t for t in labels if t != fm["category"]]
    html = md_to_html(body)

    if dry_run:
        log(f"  [DRY-RUN] {slug} | title='{title[:40]}...' | labels={labels[:5]}")
        return "dry-run"

    for attempt, wait in enumerate([0] + BACKOFF_SCHEDULE):
        if wait:
            log(f"  재시도 {attempt} (대기 {wait}s)...", "WARN")
            time.sleep(wait)
        try:
            resp = post_to_blogger(creds["blogger_blog_id"], access_token, title, html, labels)
        except requests.RequestException as e:
            log(f"  네트워크 오류: {e}", "WARN")
            continue

        if resp.status_code == 200:
            data = resp.json()
            post_id = data.get("id", "")
            log(f"  성공: {slug} → post_id={post_id}")
            return post_id

        # 401: 토큰 만료 — 한 번 갱신 후 재시도
        if resp.status_code == 401 and attempt == 0:
            log("  401 — access_token 갱신 시도", "WARN")
            access_token = refresh_access_token(
                creds["blogger_client_id"],
                creds["blogger_client_secret"],
                creds["blogger_refresh_token"],
            )
            continue

        # 403/429: rate-limit 또는 차단 — 즉시 중단
        if resp.status_code in (403, 429):
            log(f"  차단/제한 ({resp.status_code}): {resp.text[:200]}", "ERROR")
            raise RuntimeError(f"BLOCKED:{resp.status_code}")

        log(f"  실패 ({resp.status_code}): {resp.text[:200]}", "WARN")

    raise RuntimeError("업로드 실패 — 백오프 한도 초과")


# ─── 메인 실행 ────────────────────────────────────────────────────────────────
def run(time_slot, categories, delay, category_gap, daily_cap, dry_run, target_date=None):
    creds = load_credentials()
    if not creds:
        log("자격증명 없음 — 업로드 스킵 (.credentials.json 점검 필요)", "ERROR")
        return 0

    if not dry_run:
        try:
            access_token = refresh_access_token(
                creds["blogger_client_id"],
                creds["blogger_client_secret"],
                creds["blogger_refresh_token"],
            )
        except Exception as e:
            log(f"access_token 갱신 실패: {e}", "ERROR")
            return 0
    else:
        access_token = "DRY_RUN_TOKEN"

    today_count = daily_count()
    log(f"═══ Blogger 업로드 시작 — slot={time_slot}, 일일진행={today_count}/{daily_cap} ═══")

    if today_count >= daily_cap:
        log(f"일일 상한 도달 — 중단", "WARN")
        return 0

    total_posted = 0
    for idx, cat in enumerate(categories):
        if idx > 0:
            log(f"--- 카테고리 텀 {category_gap}s ---")
            time.sleep(category_gap)

        posts = pick_posts(time_slot, cat, target_date)
        log(f"[{cat}] 대상 {len(posts)}개")

        for i, (f, fm, body) in enumerate(posts):
            if today_count + total_posted >= daily_cap:
                log(f"일일 상한 도달 — 남은 {len(posts) - i}건 다음 슬롯으로 이연", "WARN")
                return total_posted
            if i > 0:
                log(f"  ...간격 {delay}s")
                time.sleep(delay)

            try:
                post_id = upload_one(f, fm, body, creds, access_token, dry_run)
                if post_id and post_id != "dry-run":
                    append_uploaded(f.stem, post_id)
                total_posted += 1
            except RuntimeError as e:
                if "BLOCKED" in str(e):
                    log("Blogger 차단 의심 — 즉시 중단, 다음 슬롯으로 이연", "ERROR")
                    return total_posted
                log(f"  실패: {e}", "ERROR")
                append_failed(f.stem, str(e))

    log(f"═══ 완료: {total_posted}건 업로드 ═══")
    return total_posted


def retry_failed(delay, dry_run):
    """실패 큐의 슬러그를 재시도"""
    if not FAILED_LOG.exists():
        log("실패 큐 없음")
        return 0
    creds = load_credentials()
    if not creds:
        log("자격증명 없음", "ERROR")
        return 0
    access_token = refresh_access_token(
        creds["blogger_client_id"], creds["blogger_client_secret"], creds["blogger_refresh_token"]
    ) if not dry_run else "DRY_RUN_TOKEN"

    failed_slugs = {line.split("\t")[0] for line in FAILED_LOG.read_text(encoding="utf-8").splitlines() if line.strip()}
    uploaded = get_uploaded_slugs()
    queue = failed_slugs - uploaded

    log(f"재시도 대상: {len(queue)}건")
    posted = 0
    for i, slug in enumerate(sorted(queue)):
        f = CONTENT_DIR / f"{slug}.md"
        if not f.exists():
            continue
        fm, body = parse_frontmatter(f.read_text(encoding="utf-8"))
        if not fm:
            continue
        if i > 0:
            time.sleep(delay)
        try:
            post_id = upload_one(f, fm, body, creds, access_token, dry_run)
            if post_id and post_id != "dry-run":
                append_uploaded(slug, post_id)
                posted += 1
        except Exception as e:
            log(f"  재시도 실패: {slug}: {e}", "ERROR")
    log(f"재시도 완료: {posted}건")
    return posted


def main():
    p = argparse.ArgumentParser(description="content/posts → Blogger 자동 업로드")
    p.add_argument("time_slot", nargs="?", choices=list(TIME_SLOT_HOUR.keys()),
                   help="시간대 (오전/점심/오후)")
    p.add_argument("--category", choices=CATEGORIES, default=None)
    p.add_argument("--all", action="store_true", help="general→it→sports→fashion 순차")
    p.add_argument("--slug", help="특정 슬러그 1건만")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--retry-failed", action="store_true")
    p.add_argument("--delay", type=int, default=DEFAULT_DELAY)
    p.add_argument("--category-gap", type=int, default=DEFAULT_CATEGORY_GAP)
    p.add_argument("--daily-cap", type=int, default=DEFAULT_DAILY_CAP)
    p.add_argument("--date", help="YYYY-MM-DD (기본: 오늘)")
    args = p.parse_args()

    if args.retry_failed:
        retry_failed(args.delay, args.dry_run)
        return

    if args.slug:
        f = CONTENT_DIR / f"{args.slug}.md"
        if not f.exists():
            log(f"파일 없음: {f}", "ERROR")
            sys.exit(1)
        creds = load_credentials()
        if not creds:
            log("자격증명 없음", "ERROR")
            sys.exit(1)
        access_token = refresh_access_token(
            creds["blogger_client_id"], creds["blogger_client_secret"], creds["blogger_refresh_token"]
        ) if not args.dry_run else "DRY_RUN_TOKEN"
        fm, body = parse_frontmatter(f.read_text(encoding="utf-8"))
        try:
            post_id = upload_one(f, fm, body, creds, access_token, args.dry_run)
            if post_id and post_id != "dry-run":
                append_uploaded(args.slug, post_id)
        except Exception as e:
            log(f"실패: {e}", "ERROR")
            append_failed(args.slug, str(e))
            sys.exit(1)
        return

    if not args.time_slot:
        p.error("time_slot 필수 (또는 --slug, --retry-failed)")

    cats = CATEGORIES if args.all else ([args.category] if args.category else ["general"])
    run(args.time_slot, cats, args.delay, args.category_gap,
        args.daily_cap, args.dry_run, args.date)


if __name__ == "__main__":
    main()
