# YouTube Channel Archive — Setup & 운영 가이드

## 개요
- **레포**: `kirus92-commits/youtube`
- **채널**: @supe-tv (623편)
- **워크플로우**: `.github/workflows/youtube-archive.yml` (6시간마다 실행)
- **출력**: 구조화된 Markdown 아카이브 (챕터, 요약, 타임스탬프 포함)

---

## 필수 설정: GitHub Secrets

**Settings → Secrets and variables → Actions → New repository secret**

| Secret Name | 값 | 설명 |
|-------------|-----|------|
| `YOUTUBE_COOKIES` | Netscape 형식 쿠키 전체 텍스트 | YouTube 봇 탐지 우회용 |

### 쿠키 추출 방법
1. 크롬에서 YouTube 로그인 상태 유지
2. 확장 프로그램 **`Get cookies.txt LOCALLY`** 설치
3. youtube.com 접속 → 확장 프로그램 클릭 → `Export` → `youtube_cookies.txt` 저장
4. 파일 열어서 전체 내용 복사 → GitHub Secrets에 붙여넣기

> ⚠️ 크롬이 실행 중이면 로컬 SQLite DB가 잠겨서 자동 추출 불가. 크롬 완전 종료 후 `python extract_cookies.py`로도 가능.

---

## 워크플로우 구조

```
.github/workflows/youtube-archive.yml
  ├─ checkout@v5
  ├─ setup-python@v6 (Python 3.11)
  ├─ setup-deno@v2 (yt-dlp JS 런타임용)
  ├─ pip install yt-dlp, youtube-transcript-api
  ├─ 쿠키 파일 생성 (secrets.YOUTUBE_COOKIES → youtube_cookies.txt)
  ├─ batch_archive_channel.py 실행
  │    ├─ 채널 업로드 플레이리스트에서 영상 ID 수집
  │    ├─ 자막 가져오기 (ko, en 우선)
  │    ├─ 챕터 자동 분할 (30초 갭 또는 3분마다)
  │    └─ 구조화된 Markdown 생성 (아카이브 폴더에 저장)
  ├─ 아티팩트 업로드 (30일 보관)
  └─ GitHub Actions Summary 생성
```

---

## 스크립트: `scripts/batch_archive_channel.py`

### 주요 옵션
```bash
python scripts/batch_archive_channel.py \
  --channel-url "https://youtube.com/@supe-tv" \
  --rate-limit 2 \           # 분당 요청 수 (기본 2)
  --max-videos 100 \         # 실행당 최대 처리 영상 수
  --language "ko,en" \       # 자막 언어 우선순위
  --output-dir ./archive_output \
  --cookies-file youtube_cookies.txt \  # 선택: 쿠키 파일
  --resume                   # 이전 진행 상태에서 재개
```

### 진행 상태 저장
- `progress_state.json`: 마지막 인덱스, 처리된 영상 ID, 성공/실패 카운트
- `archive_output/results.json`: 중간 결과
- `archive_output/summary.json`: 최종 요약 (총/성공/실패/성공률)

### 재개 기능
```bash
# 중단된 지점에서 이어서 실행
python scripts/batch_archive_channel.py ... --resume
```

---

## 로컬 테스트

```bash
# 1. 쿠키 파일 준비 (위 방법으로 추출)
# 2. 소량 테스트 (3개만)
python scripts/batch_archive_channel.py \
  --channel-url "https://youtube.com/@supe-tv" \
  --rate-limit 2 --max-videos 3 \
  --cookies-file youtube_cookies.txt

# 3. 결과 확인
ls archive_output/
cat archive_output/summary.json
```

---

## GitHub Actions에서 수동 실행

1. GitHub 레포 → Actions → `YouTube Channel Archive` 선택
2. `Run workflow` 클릭 → `Run workflow` 버튼
3. 진행 상황 Actions 탭에서 실시간 확인

---

## 트러블슈팅

| 증상 | 원인 | 해결 |
|------|------|------|
| `Sign in to confirm you're not a bot` | 쿠키 없음/만료 | Secrets에 최신 쿠키 등록 |
| `HTTP 429 Rate Limit` | 요청 과다 | `--rate-limit` 낮추기 (1~2) |
| `No formats found` | 연령 제한/비공개 영상 | 자동 스킵됨 (로그 확인) |
| `Deno not found` | setup-deno 누락 | 워크플로우에 `denoland/setup-deno@v2` 추가 |
| Node.js 20 deprecation 경고 | 구버전 액션 사용 | `actions/checkout@v5`, `actions/setup-python@v6` 사용 |

---

## 아카이브 출력 형식

각 영상별 Markdown 구조:
```
# YouTube Archive: {video_id}

**원본 URL**: https://www.youtube.com/watch?v={video_id}
**비디오 ID**: {video_id}
**아카이빙 일시**: 2026-09-22 10:30:00
**자막 언어**: ko
**총 길이**: 15:32
**세그먼트 수**: 342

---

## 📋 요약 (자동 생성)
{전체 자막 앞 500자}...

---

## 📚 챕터별 구조
### 1. 0:00 ~ 3:15
{챕터 텍스트 앞 300자}...

### 2. 3:15 ~ 6:42
...

---

## 📝 전체 자막 (타임스탬프 포함)
0:00 안녕하세요...
0:03 오늘은...

---

## 🏷️ 메타데이터
- source: youtube
- video_id: {video_id}
- archived_at: 2026-09-22T10:30:00
- tags: [youtube, archive, auto-generated]
- length_seconds: 932
```

---

## 모니터링 & 알림

- **크론**: 매주 월 09:00 `jev_openrouter_watch`와 별도
- **실패 알림**: GitHub Actions 실패 시 이메일/앱 알림 설정 권장
- **진행 상황**: Actions Summary에서 실시간 확인 가능

---

## 관련 파일 위치

| 파일 | 경로 |
|------|------|
| 워크플로우 | `.github/workflows/youtube-archive.yml` |
| 메인 스크립트 | `scripts/batch_archive_channel.py` |
| 의존성 | `requirements.txt` |
| 로컬 쿠키 템플릿 | `youtube_cookies.txt` (gitignore됨) |
| MCP 다이어그램 | `C:/Users/happi/mcp-headroom-diagram.html` |

---

## 변경 이력

| 날짜 | 변경사항 |
|------|----------|
| 2026-09-22 | 쿠키 인증 추가, deno 설정, rate limit jitter, action 버전 업그레이드 (v4→v5, v5→v6) |
| 2026-08-28 | 초기 워크플로우 생성 |

---

*최종 업데이트: 2026-09-22*