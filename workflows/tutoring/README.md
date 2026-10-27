# 수학 과외 숙제 자동 채점

구글폼 제출 → Claude가 채점 → 오답노트 시트 저장 → Discord 알림.

전체 코드는 `apps_script/Code.gs` 한 파일이에요. 서버 필요 없고, 구글이 24시간 실행해줍니다.

## 설정 (한 번만, 약 5분)

### 1. Apps Script 코드 붙여넣기
1. [구글 스프레드시트](https://docs.google.com/spreadsheets/d/1wbewy55HFxzKoRRtQdd5G5g9YG_6D19wKtcilPf66Z8/edit) 열기
2. 메뉴 → **확장 프로그램 → Apps Script**
3. 기본 `Code.gs` 내용을 전부 지우고, 이 저장소의 `apps_script/Code.gs` 내용을 붙여넣기 → 저장 (Ctrl+S)

### 2. API 키 등록
Apps Script 에디터 왼쪽 톱니바퀴(**프로젝트 설정**) → **스크립트 속성** → **속성 추가**

| 속성 이름 | 값 |
|---|---|
| `ANTHROPIC_API_KEY` | https://console.anthropic.com 에서 발급 |
| `DISCORD_WEBHOOK_URL` | Discord 채널 설정 → 연동 → 웹후크 → 새 웹후크 → URL 복사 |

### 3. 단계별 동작 확인
Apps Script 에디터 상단의 함수 선택 드롭다운에서 차례대로 실행:

1. **`testDiscord`** → Discord에 "✅ 연결 성공" 메시지 와야 함
   - 안 오면: 웹훅 URL 잘못됨 → 다시 복사해서 등록
2. **`setupSheets`** → 오답노트 시트 1행에 9개 헤더 자동 입력
3. **`setupTrigger`** → "트리거 설치 완료" 메시지가 Discord에 옴
   - 권한 요청 창 뜨면 전부 허용
   - 폼 제출 트리거 + 매주 일요일 20시 주간 리포트 트리거가 같이 설치됨
4. 구글폼에 실제 제출 → 자동으로 Discord에 채점 결과가 옴

## 자동 동작

| 언제 | 무엇이 일어나는지 |
|---|---|
| 학생이 폼 제출 | 1~2분 안에 Discord에 채점 결과 + 오답 상세, 오답노트 시트에 행 추가 |
| 매주 일요일 20시 | 지난 7일치 학생별 요약을 Discord에 한 번 전송 (`weeklyReport`) |

수동으로 주간 리포트가 필요하면 함수 드롭다운에서 `weeklyReport` 선택 → 실행.

## 시트 구조

`설문지 응답 시트1` 의 열 순서:

| A | B | C | F |
|---|---|---|---|
| 타임스탬프 | 학생 이름 | 숙제 업로드 (Drive 링크) | 단원명 |

`오답노트` 시트의 열 순서 (`setupSheets` 가 자동 설정):

| A | B | C | D | E | F | G | H | I |
|---|---|---|---|---|---|---|---|---|
| 학생 | 단원 | 날짜 | 문제번호 | 학생답안 | 정답 | 오답유형 | AI해설 | 복습완료 |

- **학생/단원/날짜**가 분리되어 있어서 필터·정렬·피벗으로 분석 가능
- **복습완료**: 학생/선생님이 다시 풀고 수동 체크하는 칸 (코드는 비워둠)

폼 응답 시트의 열 순서가 바뀌면 `Code.gs` 상단의 `COL` 객체만 고치면 됩니다.

## 문제 해결

| 증상 | 확인 방법 |
|---|---|
| Discord에 아무것도 안 옴 | Apps Script → **실행** 메뉴에서 로그 확인. 가장 최근 `onFormSubmit` 실행 클릭 → 오류 메시지 확인 |
| `testDiscord` 부터 안 됨 | 스크립트 속성에 `DISCORD_WEBHOOK_URL` 등록 확인 |
| 채점만 안 됨 | `ANTHROPIC_API_KEY` 등록 확인. 또는 Anthropic 계정에 크레딧 있는지 확인 |
| 폼 제출해도 트리거가 안 돔 | `setupTrigger` 다시 실행. 트리거 메뉴(시계 아이콘)에서 `onFormSubmit`이 등록됐는지 확인 |
| 특정 행 다시 채점하고 싶음 | `processLatestRow` 실행 (마지막 행만 재처리) |
| 주간 리포트가 일요일에 안 옴 | 트리거 메뉴에서 `weeklyReport` 가 등록됐는지 확인. 없으면 `setupTrigger` 재실행 |

## 구조

```
apps_script/
  Code.gs       ← 전체 로직 (이 파일 하나만 사용)
README.md       ← 이 문서
```
