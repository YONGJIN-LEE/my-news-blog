#!/bin/bash
# ─── 개인 블로그 자동 포스팅 + Git 배포 ─────────────────────────────────────
# 사용법: auto_post_blog.sh [시간대] [카테고리]
#   auto_post_blog.sh 오전           # 일반
#   auto_post_blog.sh 오전 it        # IT
#   auto_post_blog.sh 오전 sports    # 스포츠
#   auto_post_blog.sh 오전 fashion   # 패션
#   auto_post_blog.sh 오전 xr        # XR·AI (초안 파일명에 [XR] 태그)
#   auto_post_blog.sh 오전 all       # = focus (2026-11부터 IT·XR 주제 집중, 실행당 1개·하루 3개)
#   auto_post_blog.sh 오전 focus     # 위와 동일

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BLOG_DIR="$(dirname "$SCRIPT_DIR")"
TIME_SLOT="${1:-오전}"
CATEGORY="${2:-focus}"

echo "═══ 개인 블로그 포스팅: ${TIME_SLOT} [${CATEGORY}] ═══"

# 전체 카테고리 처리
# 네이버 블로그 운영 방침: 여러 분야를 돌지 않고 주력 주제(IT·XR)만 하루 1~3개 발행
if [ "$CATEGORY" = "all" ] || [ "$CATEGORY" = "focus" ]; then
    python3 "$SCRIPT_DIR/publish_to_blog.py" "$TIME_SLOT" --category focus
else
    python3 "$SCRIPT_DIR/publish_to_blog.py" "$TIME_SLOT" --category "$CATEGORY"
fi

# Git 커밋 & 푸시 (Cloudflare Pages 자동 배포 트리거)
cd "$BLOG_DIR"
if [ -d ".git" ]; then
    echo ""
    echo "Git 배포 중..."
    git add content/ public/
    git commit -m "포스트 추가: ${TIME_SLOT} $(date +%Y-%m-%d)" 2>/dev/null
    git push origin main 2>/dev/null
    if [ $? -eq 0 ]; then
        echo "Cloudflare Pages 배포 트리거 완료"
    else
        echo "Git push 실패 (원격 저장소 설정 확인)"
    fi
else
    echo ""
    echo "Git 미설정 — 로컬 빌드만 완료. 배포하려면 Git 초기화 필요."
    echo "  cd $BLOG_DIR && git init && git remote add origin <repo-url>"
fi

echo ""
echo "═══ 완료 ═══"
echo "로컬 확인: open $BLOG_DIR/public/index.html"
