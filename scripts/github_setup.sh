#!/bin/bash
# GitHub 리포지토리 생성 및 초기 push 스크립트
# 용진님 Mac 터미널에서 실행하세요

set -e

BLOG_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$BLOG_DIR"

echo "=== 개인 블로그 GitHub 리포지토리 셋업 ==="
echo ""

# 1. gh CLI 확인
if ! command -v gh &> /dev/null; then
    echo "❌ GitHub CLI(gh)가 설치되어 있지 않습니다."
    echo "   설치: brew install gh"
    echo "   인증: gh auth login"
    exit 1
fi

# 2. gh 인증 확인
if ! gh auth status &> /dev/null 2>&1; then
    echo "❌ GitHub에 로그인되어 있지 않습니다."
    echo "   실행: gh auth login"
    exit 1
fi

echo "✅ GitHub CLI 인증 확인 완료"

# 3. git 초기화
if [ ! -d ".git" ]; then
    git init
    echo "✅ Git 초기화 완료"
else
    echo "✅ Git 이미 초기화됨"
fi

# 4. 파일 추가 및 첫 커밋
git add -A
git commit -m "Initial commit: 오늘의 뉴스 브리핑 개인 블로그

- Apple 스타일 디자인 (frosted glass header, card layout)
- 320+ 뉴스 포스트 (2026-03-26 ~ 2026-04-02)
- Python 기반 정적 사이트 빌더 (build_html.py)
- 자동 포스팅 스크립트 (publish_to_blog.py)
- Cloudflare Pages 배포 준비 완료"

echo "✅ 첫 커밋 완료"

# 5. GitHub 리포 생성 (public)
REPO_NAME="my-news-blog"
echo ""
echo "📦 GitHub 리포지토리 생성 중: $REPO_NAME"

gh repo create "$REPO_NAME" --public --source=. --remote=origin --push

echo ""
echo "=== 셋업 완료! ==="
echo ""
echo "🌐 리포지토리: https://github.com/$(gh api user -q .login)/$REPO_NAME"
echo ""
echo "다음 단계: Cloudflare Pages에서 이 리포를 연결하세요."
echo "  1. https://dash.cloudflare.com → Pages → Create a project"
echo "  2. Connect to Git → $REPO_NAME 선택"
echo "  3. Build settings:"
echo "     - Build command: (비워두기)"
echo "     - Build output directory: public"
echo "  4. Save and Deploy"
