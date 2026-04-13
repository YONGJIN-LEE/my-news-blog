# 필수 이미지 자산

정식 서비스 전환 전 아래 파일을 추가해야 합니다. 파일명은 `hugo.toml`·`layouts/partials/head.html`과 일치해야 합니다.

| 파일 | 용도 | 권장 사양 |
|------|------|-----------|
| `og-default.png` | 썸네일 없는 포스트의 기본 Open Graph 이미지 | 1200×630, PNG/JPG |
| `logo.png` | JSON-LD publisher 로고 (Google 검색 결과 표시) | 최소 600×60, PNG (투명 배경) |
| `../favicon.ico` | 브라우저 탭 아이콘 (static 루트에 배치) | 32×32 / 48×48 멀티 |
| `../apple-touch-icon.png` | iOS 홈 화면 아이콘 (static 루트) | 180×180 PNG |

## 생성 팁

- 간단히 만들 경우: Canva, Figma, 또는 `scripts/stitch_generate.mjs`로 자동 생성
- 로고는 사이트 제목 텍스트 로고로 충분. 흑백 대비 확보 필요
