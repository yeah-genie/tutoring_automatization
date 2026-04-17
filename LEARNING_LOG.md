# 데이터 분석 학습 기록 — 과외 자동화 프로젝트

> AI 시대 데이터 분석가의 핵심 역량인 **Privacy by Design**과 **데이터 거버넌스**를
> 실제 운영 중인 프로젝트에 적용하며 학습한 기록.

---

## 프로젝트 개요

수학 과외 학생들의 숙제를 자동으로 채점하고 분석하는 시스템.

| 항목 | 내용 |
|------|------|
| 학생 수 | 5명 |
| 주요 기술 | Claude Vision API, Google Sheets/Drive, OpenCV, scikit-learn |
| 자동화 범위 | 숙제 채점 → 오답 분석 → 이상탐지 → 리포트 생성 |

---

## 학습 로드맵

- [x] **1단계** 학생 실명 비식별화 (Privacy by Design)
- [ ] **2단계** 데이터 생애주기 관리 (보존 기간 + 자동 삭제)
- [ ] **3단계** 차등 프라이버시 (Differential Privacy) 적용
- [ ] **4단계** 데이터 품질 관리 파이프라인
- [ ] **5단계** ML 평가지표 검증 고도화

---

## 1단계: 학생 실명 비식별화

**날짜:** 2026-04-17

### 발견한 문제

코드 감사(Code Audit)를 통해 두 가지 프라이버시 이슈 발견.

**이슈 1 — 하드코딩된 학생 실명 (심각도: 높음)**

```python
# main.py — 변경 전
STUDENT_DRIVE_FOLDERS = {
    "양서연": "17zOlV9g...",
    "김준서": "1jlZE4R2...",
    ...  # 실명 5개가 코드에 직접 박혀있었음
}
```

코드는 GitHub 같은 버전 관리 시스템에 올라갈 수 있고, 히스토리에 한번 포함되면 나중에 지워도 추적 가능. 미성년 학생 실명이 공개될 위험.

**이슈 2 — 외부 API로 실명 전송 (심각도: 중간)**

```python
# 변경 전: Claude API로 실명이 그대로 전송됨
prompt = f"학생 이름: {student_name} ..."  # "학생 이름: 박나인"
```

Claude API는 Anthropic 서버로 데이터가 전송됨. 미성년자 학생 실명이 제3자 서버 로그에 남을 수 있음.

---

### 적용한 개념

**데이터 최소화 (Data Minimization)**
각 시스템 레이어에는 그 레이어가 필요로 하는 최소한의 데이터만 있어야 한다는 원칙. GDPR 제5조에서 요구.

- 코드 레이어 → 학생 이름 불필요 (`.env`로 분리)
- 외부 API 레이어 → 실명 불필요 (익명 ID로 대체)

**Privacy by Design**
보안을 나중에 덧붙이는 게 아니라, 시스템 설계 단계부터 개인정보 보호를 내재화하는 방식.

---

### 변경 내용

**① 코드에서 `.env`로 분리**

```
변경 전: main.py 코드 안에 학생 이름 하드코딩
변경 후: .env 파일 (gitignore 대상) 에 JSON으로 저장

STUDENT_DRIVE_FOLDERS={"양서연": "폴더ID", ...}
```

`config.py`에 파싱 로직 추가:
```python
def _parse_student_folders() -> dict[str, str]:
    raw = os.getenv("STUDENT_DRIVE_FOLDERS", "{}")
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {}
```

**② Anonymizer 클래스 생성** (`modules/anonymizer.py`)

```python
class Anonymizer:
    # 실명 → STU_001, STU_002, ... 로 변환
    # 역방향 복원도 지원

    def mask(self, name: str) -> str: ...     # "박나인" → "STU_004"
    def unmask(self, anon_id: str) -> str: ... # "STU_004" → "박나인"
    def mask_dict(self, data: dict) -> dict: ...
```

**③ grader.py — API 호출 전 실명 치환**

```python
# analyze_patterns, generate_weekly_report,
# generate_monthly_report_draft 모두 적용

prompt = pattern_analysis_prompt(self._anon.mask(student_name), wrong_answers)
#                                 ↑ "박나인" 대신 "STU_004" 전송
```

---

### 결과

| 구분 | 변경 전 | 변경 후 |
|------|--------|--------|
| 코드 내 학생 이름 | 5개 하드코딩 | 0개 (`.env`로 이동) |
| Claude API 전송값 | `학생: 박나인` | `학생: STU_004` |
| git 히스토리 노출 | 위험 | 없음 |

---

### 배운 것

- **코드 감사**란 무엇인가: 시스템의 데이터 흐름을 추적해서 개인정보가 불필요하게 노출되는 지점을 찾아내는 과정
- **`.env` 패턴**: 민감한 설정값(API 키, 개인정보 포함 설정)을 코드와 분리하는 표준적인 방법
- **익명화(Anonymization) vs 가명화(Pseudonymization)**: 이 프로젝트에서 한 건 가명화(STU_001처럼 역변환 가능한 ID 부여). 완전한 익명화는 역변환이 불가능해야 함. GDPR에서는 두 개념을 다르게 취급함.

---

## 2단계: 데이터 생애주기 관리

**날짜:** 2026-04-17

### 발견한 문제

현재 SQLite DB에는 삭제 로직이 전혀 없음. 과외가 끝난 학생 데이터, 1년 전 숙제 기록이 영구적으로 축적됨.

### 적용한 개념

**보존 기간 제한 원칙 (GDPR 제5조(e))**
개인정보는 수집 목적을 달성한 후 더 이상 보관되어서는 안 된다. 이 프로젝트에서 "목적" = 과외 진행 중 학습 분석. 과외 종료 후에는 보관 근거가 없어짐.

**잊혀질 권리 (GDPR 제17조 / Right to Erasure)**
정보 주체(학생/학부모)가 요청하면 모든 관련 데이터를 지체 없이 삭제해야 할 의무.
특히 미성년자 데이터는 법정대리인(부모)이 삭제 요청 가능.

**데이터 생애주기 (Data Lifecycle)**
```
수집 → 저장 → 활용 → [보존 기간 초과 or 삭제 요청] → 삭제
```

### 변경 내용

**`modules/db.py`에 추가한 메서드 3개:**

```python
# 1. N일 이상 된 데이터 자동 정리 (보존 기간 정책)
db.purge_old_data(retention_days=365)
# → sessions, anomaly_alerts, file_hashes, processed_rows에서
#   1년 이상 된 레코드 전부 삭제

# 2. 특정 학생 전체 데이터 삭제 (잊혀질 권리)
db.delete_student_data("박나인")
# → 해당 학생의 모든 테이블 레코드 삭제

# 3. 현황 파악 (어떤 학생 데이터가 얼마나 오래됐는지)
db.get_data_summary()
# → [{"student_name": "박나인", "session_count": 12,
#     "oldest": "2025-03-01", "latest": "2026-04-10"}, ...]
```

**`main.py`에 CLI 커맨드 추가:**

```bash
# 1년 이상 된 데이터 정리
python main.py --purge 365

# 특정 학생 데이터 전체 삭제
python main.py --delete-student 박나인
```

### 결과

| 기능 | 이전 | 이후 |
|------|------|------|
| 오래된 데이터 정리 | 수동으로 DB 파일 삭제밖에 없음 | `--purge N` 커맨드 |
| 학생 데이터 삭제 | 불가능 | `--delete-student 이름` 커맨드 |
| 데이터 현황 파악 | 없음 | `get_data_summary()` |

### 배운 것

- **GDPR 제5조 vs 제17조의 차이**: 5조는 "자동으로 지워야 한다"(시스템 정책), 17조는 "요청받으면 지워야 한다"(사람 대응). 둘 다 구현해야 완전한 거버넌스.
- **정책을 코드로 강제하는 것**: "1년 뒤 지운다"는 말만 하는 게 아니라, `--purge 365` 커맨드로 실제 실행 가능하게 만드는 것이 진짜 거버넌스.
- **데이터 생애주기 관리의 현실적 어려움**: 삭제하면 이상탐지 기준 데이터도 줄어듦. 보존과 삭제 사이의 균형점을 찾는 게 거버넌스 담당자의 판단 영역.

---

## 3단계: 차등 프라이버시 (Differential Privacy)

*작성 예정*

---

## 참고 자료

- [OpenMined — Private AI 커뮤니티](https://www.openmined.org)
- [Google Differential Privacy 라이브러리](https://github.com/google/differential-privacy)
- GDPR 제5조 (데이터 처리 원칙)
- NIST Privacy Framework
