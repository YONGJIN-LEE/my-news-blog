# 개인 블로그 구축 가이드

## 아키텍처 개요

```
drafts/*.md → publish_to_blog.py → content/posts/*.md (Hugo 포맷)
                                  → build_html.py → public/*.html
                                  → git push → Cloudflare Pages 자동 배포
                                  → 브라우저에서 복사 → 네이버 블로그 붙여넣기
```

## 1단계: 로컬 환경 설정 (5분)

### Python 빌더만 사용 (Hugo 없이)
이미 Python이 설치되어 있으므로 바로 사용 가능합니다.

```bash
# 테스트 실행
cd ~/blog/my-blog
python3 scripts/publish_to_blog.py 오전

# 결과 확인 (브라우저에서 열기)
open public/index.html
```

### Hugo 설치 (선택사항 — 더 빠른 빌드)
```bash
# macOS
brew install hugo

# 빌드 테스트
cd ~/blog/my-blog
hugo server -D
# → http://localhost:1313 에서 미리보기
```

## 2단계: GitHub 저장소 생성 (10분)

```bash
cd ~/blog/my-blog
git init
git add .
git commit -m "초기 블로그 설정"

# GitHub에서 새 저장소 생성 후
git remote add origin https://github.com/YOUR_USERNAME/my-blog.git
git branch -M main
git push -u origin main
```

## 3단계: Cloudflare Pages 배포 (15분)

1. **Cloudflare 계정 생성**: https://dash.cloudflare.com/sign-up
2. **Workers & Pages** → **Create** → **Connect to Git**
3. **GitHub 연결** → `my-blog` 저장소 선택
4. **빌드 설정**:
   - Framework: `Hugo` (Hugo 사용 시) 또는 `None` (Python 빌더 사용 시)
   - Build command: `hugo --minify` 또는 `python3 scripts/build_html.py`
   - Output directory: `public`
5. **Deploy** 클릭

### 커스텀 도메인 연결
1. **도메인 구매**: Cloudflare Registrar, 가비아, 후이즈 등
   - 추천: Cloudflare Registrar (원가, 추가 비용 없음)
   - .com 도메인: 연 약 $10 (약 13,000원)
2. Cloudflare Pages → **Custom domains** → 도메인 추가
3. DNS 자동 설정 완료

## 4단계: 기존 파이프라인 연동

### 방법 A: generate_all.sh에 추가 (자동)
`~/blog/scripts/generate_all.sh`에 다음을 추가:

```bash
# ─── 기존 Blogger 포스팅 후에 추가 ─────────────────
# 개인 블로그 포스팅 (Blogger 실패 시 백업 + 네이버 복사용)
echo "=== 개인 블로그 포스팅 ==="
~/blog/my-blog/scripts/auto_post_blog.sh "$TIME_SLOT" all
```

### 방법 B: 별도 실행 (수동)
```bash
# 전체 카테고리
~/blog/my-blog/scripts/auto_post_blog.sh 오전 all

# 개별 카테고리
~/blog/my-blog/scripts/auto_post_blog.sh 오전 general
~/blog/my-blog/scripts/auto_post_blog.sh 오전 it
~/blog/my-blog/scripts/auto_post_blog.sh 오전 sports
~/blog/my-blog/scripts/auto_post_blog.sh 오전 fashion
```

## 5단계: Unsplash 이미지 설정 (선택)

기본적으로 picsum.photos의 무료 이미지를 사용합니다.
키워드 기반 고품질 이미지를 원하면:

1. https://unsplash.com/developers 에서 앱 생성
2. Access Key 복사
3. 환경변수 설정:
```bash
export UNSPLASH_ACCESS_KEY="your-access-key-here"

# .zshrc에 영구 추가
echo 'export UNSPLASH_ACCESS_KEY="your-key"' >> ~/.zshrc
```

## 네이버 블로그 복사 워크플로우

1. 개인 블로그 접속 (https://yourdomain.com)
2. 포스트 열기
3. 본문 전체 선택 (Cmd+A)
4. 복사 (Cmd+C)
5. 네이버 블로그 → 새 글 → 붙여넣기 (Cmd+V)
6. 서식(제목, 소제목, 굵기)과 이미지가 그대로 유지됨

## 폴더 구조

```
my-blog/
├── hugo.toml              ← Hugo 설정 (사이트 제목, URL 등)
├── SETUP_GUIDE.md         ← 이 가이드
├── content/posts/         ← Hugo 포맷 포스트 (자동 생성)
├── layouts/               ← Hugo 템플릿
│   ├── _default/
│   │   ├── baseof.html
│   │   ├── list.html
│   │   └── single.html
│   └── partials/
├── static/
│   └── css/style.css      ← 블로그 스타일
├── scripts/
│   ├── publish_to_blog.py ← 메인 포스팅 스크립트
│   ├── build_html.py      ← Python HTML 빌더 (Hugo 대체)
│   └── auto_post_blog.sh  ← 자동 포스팅 + 배포
└── public/                ← 빌드 결과 (HTML 파일들)
```

## 비용 요약

| 항목 | 비용 |
|------|------|
| Cloudflare Pages 호스팅 | **무료** |
| 커스텀 도메인 (.com) | **연 ~13,000원** |
| Unsplash API | **무료** (시간당 50회) |
| **합계** | **연 ~13,000원** |

## 장기 확장 계획

- **광고 수익화**: Google AdSense 코드를 템플릿에 추가
- **검색 최적화**: sitemap.xml, robots.txt 자동 생성 (Hugo 기본 지원)
- **다크모드**: CSS 변수로 간단히 추가 가능
- **댓글**: Disqus 또는 giscus(GitHub) 연동
- **WordPress 전환**: 도메인 유지한 채 WordPress로 마이그레이션 가능
