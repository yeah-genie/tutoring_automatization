# 수학 과외 자동화 시스템 — 세팅 가이드

## 0. 전체 흐름 요약

```
학생이 구글폼 제출
    → Google Sheets에 자동 기록
    → Python이 새 행 감지 (60초마다 폴링)
    → Google Drive에서 파일 다운로드
    → 중복 검사 (MD5 + 지각적 해시)
    → 이미지 전처리 (기울기 보정, 대비 향상)
    → Claude Vision으로 채점
    → Sheets 오답노트 저장
    → Discord 알림 전송
    ↓ (매주 일요일 오후 8시)
    주간 리포트 Discord 전송
    ↓ (필요할 때 수동 실행)
    월간 리포트 초안 Notion 생성 + Discord 알림
```

---

## 1. Python 환경 세팅

```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

---

## 2. Google API 설정 (서비스 계정)

### 2-1. Google Cloud Console에서 서비스 계정 만들기

1. [Google Cloud Console](https://console.cloud.google.com/) 접속
2. 새 프로젝트 생성 (예: `tutoring-automation`)
3. **API 및 서비스 → 라이브러리** 에서 다음 두 API 활성화:
   - **Google Sheets API**
   - **Google Drive API**
4. **IAM 및 관리자 → 서비스 계정** → 새 서비스 계정 생성
5. 서비스 계정 → **키 추가 → JSON** → 다운로드
6. 다운로드한 JSON 파일을 프로젝트 폴더에 `service_account.json` 이름으로 저장

### 2-2. 스프레드시트에 서비스 계정 공유

1. 서비스 계정 JSON 파일 안의 `client_email` 값 복사
   (예: `tutoring@tutoring-automation.iam.gserviceaccount.com`)
2. 구글 스프레드시트 열기 → 공유 → 해당 이메일 추가 (편집자 권한)

---

## 3. Claude API 키

1. [Anthropic Console](https://console.anthropic.com/) 접속
2. **API Keys** → 새 키 생성
3. `config.py`의 `ANTHROPIC_API_KEY`에 입력

---

## 4. Discord 웹훅 설정

1. 알림 받을 Discord 서버에서 채널 선택
2. **채널 편집 → 연동 → 웹훅 → 새 웹훅** 생성
3. 웹훅 URL 복사
4. `config.py`의 `DISCORD_WEBHOOK_URL`에 입력

---

## 5. KakaoTalk 나에게 보내기 토큰 발급

1. [Kakao Developers](https://developers.kakao.com/) 접속 → 내 애플리케이션 → 앱 추가
2. **플랫폼 → Web** → 사이트 도메인: `http://localhost`
3. **제품 설정 → 카카오 로그인** → 활성화 ON
4. **Redirect URI**: `http://localhost`
5. 아래 URL을 브라우저에서 열어서 인증 후 코드 발급:
   ```
   https://kauth.kakao.com/oauth/authorize?client_id=YOUR_REST_API_KEY&redirect_uri=http://localhost&response_type=code
   ```
6. 리다이렉트된 URL에서 `code=` 뒤의 값 복사
7. 아래 명령으로 액세스 토큰 발급:
   ```bash
   curl -X POST https://kauth.kakao.com/oauth/token \
     -d "grant_type=authorization_code" \
     -d "client_id=YOUR_REST_API_KEY" \
     -d "redirect_uri=http://localhost" \
     -d "code=YOUR_CODE"
   ```
8. 응답의 `access_token` 값을 `config.py`의 `KAKAO_ACCESS_TOKEN`에 입력

> **주의:** 액세스 토큰은 만료됩니다. 만료 시 리프레시 토큰으로 갱신이 필요합니다.

---

## 6. Notion 설정

### 6-1. 인테그레이션 토큰 발급

1. [Notion 개발자 페이지](https://www.notion.so/my-integrations) → 새 인테그레이션 생성
2. 이름: `tutoring-automation` / 연결할 워크스페이스 선택
3. **저장 → 토큰 복사**
4. `config.py`의 `NOTION_TOKEN`에 입력

### 6-2. Notion 데이터베이스 생성

1. Notion에서 새 페이지 생성 → **데이터베이스 — 전체 페이지** 선택
2. 데이터베이스 이름: `수학 과외 리포트`
3. 다음 속성 추가 (기본 Name은 그대로):

   | 속성명 | 유형 |
   |--------|------|
   | 학생 | 텍스트 |
   | 월 | 텍스트 |
   | 상태 | 선택 (값: `검토 필요`, `검토 완료`) |
   | 생성일 | 날짜 |

4. 데이터베이스 URL에서 ID 복사:
   `https://notion.so/YOUR_DATABASE_ID?v=...`
5. `config.py`의 `NOTION_DATABASE_ID`에 입력
6. 데이터베이스 페이지 오른쪽 상단 `...` → **연결** → 만들어 둔 인테그레이션 추가

---

## 7. 구글폼 컬럼명 확인

`config.py`의 `FORM_COLUMNS`를 실제 구글폼 응답 시트의 열 제목과 맞추세요.

```python
FORM_COLUMNS = {
    "timestamp": "타임스탬프",      # 폼에서 자동 생성
    "student_name": "이름",         # 폼 질문 제목
    "subject": "과목",
    "homework_title": "숙제 제목",
    "file_links": "파일 업로드",    # Drive 링크 질문 제목
}
```

스프레드시트 열 제목과 정확히 일치해야 합니다.

---

## 8. 오답노트 시트 컬럼 준비

스프레드시트의 `오답노트` 시트에 아래 헤더를 1행에 추가하세요:

```
날짜 | 학생 이름 | 숙제제목 | 문제번호 | 오답유형 | 학생답안 | 정답 | 피드백
```

---

## 9. 실행

```bash
# 상시 실행 (폴링 + 자동 스케줄)
python main.py

# 한 번만 실행 (새 제출 처리)
python main.py --once

# 주간 리포트 즉시 생성
python main.py --weekly

# 특정 학생 월간 리포트 초안 생성
python main.py --monthly 홍길동 2025 11
```

---

## 10. 주요 파일 구조

```
tutoring_automation/
├── main.py                  ← 실행 진입점
├── config.py                ← API 키 및 설정 (이 파일 수정)
├── requirements.txt
├── service_account.json     ← Google 서비스 계정 키 (직접 추가)
├── SETUP.md                 ← 이 가이드
├── modules/
│   ├── duplicate_checker.py ← 중복 파일 감지
│   ├── image_processor.py   ← 이미지 전처리 (OpenCV)
│   ├── sheets_monitor.py    ← Sheets 폴링 + Drive 다운로드
│   ├── grader.py            ← Claude Vision 채점
│   ├── notifiers.py         ← Discord + 카카오톡
│   └── notion_reporter.py   ← 월간 리포트 Notion 생성
└── prompts/
    └── grading_prompt.py    ← 채점/분석/리포트 프롬프트
```

---

## 자주 묻는 것들

**Q. 카카오 토큰이 만료됐어요.**
A. 카카오 토큰은 보통 6시간 유효합니다. 리프레시 토큰으로 갱신하거나, Discord 알림만으로도 충분합니다.

**Q. 이미지 품질이 낮다는 Discord 알림이 계속 와요.**
A. `config.py`의 `MIN_IMAGE_QUALITY_SCORE`를 낮추면 됩니다 (기본값 30).

**Q. Notion 페이지 속성이 이미 있는 속성과 달라서 오류가 나요.**
A. `notion_reporter.py`의 `create_monthly_draft` 함수 안 `properties`를 실제 데이터베이스 속성명에 맞게 수정하세요.
