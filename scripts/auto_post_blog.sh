#!/bin/bash
# ─── 개인 블로그 자동 포스팅 + Git 배포 ─────────────────────────────────────
# 사용법: auto_post_blog.sh [시간대] [카테고리]
#   auto_post_blog.sh 오전           # 일반
#   auto_post_blog.sh 오전 it        # IT
#   auto_post_blog.sh 오전 sports    # 스포츠
#   auto_post_blog.sh 오전 fashion   # 패션
#   auto_post_blog.sh 오전 all       # 전체 카테고리

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BLOG_DIR="$(dirname "$SCRIPT_DIR")"
TIME_SLOT="${1:-오전}"
CATEGORY="${2:-general}"

echo "═══ 개인 블로그 포스팅: ${TIME_SLOT} [${CATEGORY}] ═══"

# 전체 카테고리 처리
if [ "$CATEGORY" = "all" ]; then
    for cat in general it sports fashion; do
        echo "--- ${cat} ---"
        python3 "$SCRIPT_DIR/publish_to_blog.py" "$TIME_SLOT" --category "$cat"
        sleep 1
    done
else
    python3 "$SCRIPT_DIR/publish_to_blog.py" "$TIME_SLOT" --category "$CATEGORY"
fi

# Git 커밋 & 푸시 (Cloudflare Pages 자동 배포 트리거)
cd "$BLOG_DIR"
if [ -d ".git" ]; then
    echo ""
    echo "Git 배포 중..."
    git add content/
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
