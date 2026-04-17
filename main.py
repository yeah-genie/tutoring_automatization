"""
수학 과외 숙제 자동화 시스템 — 진입점

실행 방법:
  python main.py          # 상시 실행 (Sheets 폴링 + 스케줄)
  python main.py --once   # 새 제출 한 번만 처리 후 종료
  python main.py --weekly # 주간 리포트 즉시 생성
  python main.py --monthly 홍길동 2025 11  # 월간 리포트 초안 생성
  streamlit run student_dashboard.py      # 대시보드 실행
"""

import argparse
import logging
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import schedule

import config
from modules.anomaly_detector import AnomalyDetector
from modules.db import Database
from modules.duplicate_checker import DuplicateChecker
from modules.grader import Grader
from modules.image_processor import prepare_files_for_grading
from modules.notifiers import Notifiers
from modules.notion_reporter import NotionReporter
from modules.pdf_generator import ExamPDFGenerator
from modules.sheets_monitor import SheetsMonitor
from prompts.grading_prompt import HOMEWORK_SUGGESTION_SYSTEM, homework_suggestion_prompt

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("tutoring_automation.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)


def _check_config():
    """필수 설정값이 비어있으면 경고."""
    missing = []
    if not config.ANTHROPIC_API_KEY:
        missing.append("ANTHROPIC_API_KEY")
    if not config.SPREADSHEET_ID:
        missing.append("SPREADSHEET_ID")
    if missing:
        logger.warning("설정 누락: %s — .env 파일을 확인해주세요.", ", ".join(missing))
        return False
    return True


def process_new_submissions(
    monitor: SheetsMonitor,
    grader: Grader,
    dup_checker: DuplicateChecker,
    notifiers: Notifiers,
    detector: AnomalyDetector,
    db: Database,
):
    """새 폼 제출을 처리하는 메인 루프 1회 실행."""
    found_new = False

    for submission in monitor.get_new_submissions():
        found_new = True
        student = submission["student_name"]
        homework = submission["homework_title"]
        row_num = submission["row_number"]
        logger.info("새 제출 — %s: %s (행 %d)", student, homework, row_num)

        try:
            _process_single_submission(
                submission, monitor, grader, dup_checker, notifiers, detector, db
            )
            db.mark_processed(row_num, student, "success")
        except Exception as e:
            logger.error("처리 실패 (행 %d): %s", row_num, e, exc_info=True)
            # 실패한 행은 'failed' 로 기록 → 나중에 --retry 옵션으로 재처리 가능
            db.mark_processed(row_num, student, "failed")
            if student == "박나인":
                notifiers.discord(f"❌ 처리 실패 — {student} / {homework}\n오류: {e}")

    if not found_new:
        logger.debug("새 제출 없음")


STUDENT_DRIVE_FOLDERS = {
    "양서연": "17zOlV9g_C9nPvdW7J_g9vzqBZ4gWqs5T",
    "김준서": "1jlZE4R2LTQZUf8gaheFjEiEfqpRTBBCd",
    "김하원": "1HWyIePa3oFwdNMeM9wrXJ97YpEif3r3J",
    "박나인": "12JH_u8YON0ZbLZcMcC_08CQOw7EEO3dg",
    "엄지후": "1o9MJQyOPrwLk0T6NgfZUNdDBOzA0PMmX",
}


def _process_single_submission(
    submission: dict,
    monitor: SheetsMonitor,
    grader: Grader,
    dup_checker: DuplicateChecker,
    notifiers: Notifiers,
    detector: AnomalyDetector,
    db: Database,
):
    student = submission["student_name"]
    homework = submission["homework_title"]
    discord_enabled = (student == "박나인")

    # ① Drive 파일 다운로드 (새 파일명 형식: YYYYMMDD_학생_단원_페이지.ext)
    downloaded: list[Path] = []
    for i, file_id in enumerate(submission["file_ids"], start=1):
        path = monitor.download_drive_file(file_id, student, unit=homework, page=i)
        if path:
            downloaded.append(path)

    if not downloaded:
        logger.warning("다운로드된 파일 없음 — 건너뜀")
        return

    # ② 중복 검사
    valid_files: list[Path] = []
    for path in downloaded:
        is_dup, reason = dup_checker.is_duplicate(path, student)
        if is_dup:
            logger.info("중복 제외: %s — %s", path.name, reason)
            if discord_enabled:
                notifiers.discord_duplicate_detected(student, path.name, reason)
        else:
            dup_checker.register(path, student)
            valid_files.append(path)

    if not valid_files:
        logger.info("유효한 파일 없음 (모두 중복)")
        return

    # ③ 이미지 전처리 + 품질 확인
    prepared = prepare_files_for_grading(valid_files)
    grading_files: list[Path] = []
    for processed_path, quality_score in prepared:
        if quality_score < config.MIN_IMAGE_QUALITY_SCORE and discord_enabled:
            notifiers.discord_low_quality(student, processed_path.name, quality_score)
        grading_files.append(processed_path)

    # ④ Claude Vision 채점
    logger.info("채점 시작 — %s, 파일 %d개", student, len(grading_files))
    result = grader.grade_submission(grading_files)

    if not result.get("problems") and "error" in result:
        raise RuntimeError(f"채점 실패: {result['error']}")

    problems = result.get("problems", [])

    # ⑤ 오답노트 저장 (Sheets)
    monitor.append_wrong_answers(student, homework, problems)

    # ⑥ 세션 요약 저장 (SQLite — 이상탐지 피처로 사용)
    error_type_counts: dict[str, int] = {}
    for p in problems:
        if not p.get("is_correct") and p.get("error_type"):
            t = p["error_type"]
            error_type_counts[t] = error_type_counts.get(t, 0) + 1

    session_id = db.save_session(
        student_name=student,
        homework_title=homework,
        submitted_at=datetime.now().strftime("%Y-%m-%d"),
        total_problems=result.get("total_problems", len(problems)),
        correct_count=result.get("correct_count", 0),
        error_type_counts=error_type_counts,
    )

    # ⑦ Discord 채점 완료 + 해설 알림 (박나인만)
    if discord_enabled:
        notifiers.discord_grading_with_explanation(student, homework, result)

    # ⑦-b 숙제 추천 + 시험지 PDF 생성 + Discord 전송 (박나인만)
    _generate_and_send_homework(student, homework, monitor, grader, notifiers, discord_enabled=discord_enabled)

    # ⑧ 이상탐지 실행
    sessions = db.get_sessions(student)
    alerts = detector.detect(student, sessions)
    if alerts:
        if discord_enabled:
            notifiers.discord_anomaly_alerts(alerts)
        for a in alerts:
            db.save_alert(
                student_name=a.student_name,
                alert_type=a.alert_type,
                severity=a.severity,
                score=a.score,
                description=a.description,
                recommendation=a.recommendation,
                session_id=session_id,
            )

    logger.info("처리 완료 — %s", student)


def _generate_and_send_homework(
    student: str,
    unit: str,
    monitor: SheetsMonitor,
    grader: Grader,
    notifiers: Notifiers,
    discord_enabled: bool = True,
):
    """오답 기반 숙제 추천 → 시험지/해설지 PDF → Discord + Drive."""
    try:
        import re as _re
        import anthropic as _anthropic

        # 오답 이력 + 복습 후보
        wrong_history = monitor.get_wrong_answer_history(student, wrong_only=True)
        review_candidates = monitor.get_review_candidates(student, limit=2)

        # Claude로 숙제 추천 생성
        client = _anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
        hw_resp = client.messages.create(
            model=config.CLAUDE_MODEL,
            max_tokens=800,
            system=HOMEWORK_SUGGESTION_SYSTEM,
            messages=[{"role": "user", "content": homework_suggestion_prompt(student, wrong_history, unit)}],
        )
        raw = hw_resp.content[0].text
        match = _re.search(r"\{.*\}", raw, _re.DOTALL)
        suggestion = grader._parse_json_response(raw) if match else {}

        if not suggestion.get("assignments"):
            logger.warning("숙제 추천 파싱 실패 — PDF 생성 건너뜀")
            return

        assignments = suggestion["assignments"]

        # 복습 문제 추가
        if review_candidates:
            types = ", ".join(set(r.get("오답유형", "") for r in review_candidates if r.get("오답유형")))
            assignments.append({
                "type": f"REVIEW — Previous errors ({types or 'mixed'})",
                "count": len(review_candidates),
                "difficulty": "Foundation",
                "note": "Based on recent mistakes — mark cao only",
            })

        # 숙제 추천 Discord 전송 (박나인만)
        if discord_enabled:
            notifiers.discord_homework_suggestion(student, suggestion)

        # PDF 생성
        gen = ExamPDFGenerator()
        paths = gen.generate(student, unit, assignments)

        # Drive 업로드 후 Discord 전송 (박나인만)
        paper_url = monitor.upload_pdf_to_student_folder(
            paths["paper"], student, STUDENT_DRIVE_FOLDERS
        )
        if discord_enabled:
            notifiers.discord_exam_ready(student, unit, paths["paper"], paths["markscheme"], paper_url or "")

    except Exception as e:
        logger.error("숙제 PDF 생성 실패 — %s: %s", student, e, exc_info=True)
        if discord_enabled:
            notifiers.discord(f"⚠️ Homework PDF 생성 실패 — {student}\n{e}")


def run_weekly_report(monitor: SheetsMonitor, grader: Grader, notifiers: Notifiers):
    week_start = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
    logger.info("주간 리포트 생성 (%s 이후)...", week_start)

    students_data = monitor.get_all_students_weekly(week_start)
    if not students_data:
        notifiers.discord("📊 이번 주 제출된 숙제가 없습니다.")
        return

    report = grader.generate_weekly_report(week_start, students_data)
    notifiers.discord_weekly_report(report)
    logger.info("주간 리포트 전송 완료")


def run_monthly_report(
    student_name: str,
    year: int,
    month: int,
    monitor: SheetsMonitor,
    grader: Grader,
    notifiers: Notifiers,
    notion: NotionReporter,
    db: Database,
):
    month_label = f"{year}년 {month}월"
    logger.info("월간 리포트 초안 생성 — %s %s", student_name, month_label)

    wrong_answers = monitor.get_monthly_data(student_name, year, month)
    history = monitor.get_wrong_answer_history(student_name)
    pattern = grader.analyze_patterns(student_name, history)
    draft = grader.generate_monthly_report_draft(student_name, month_label, wrong_answers, pattern)

    if not draft or "parse_error" in draft:
        notifiers.discord(f"❌ {student_name} 월간 리포트 초안 생성 실패")
        return

    notion_url = notion.create_monthly_draft(student_name, year, month, draft, pattern)
    notifiers.discord_monthly_draft_ready(student_name, notion_url)
    logger.info("Notion 초안 생성 완료: %s", notion_url)


def main():
    parser = argparse.ArgumentParser(description="수학 과외 숙제 자동화 시스템")
    parser.add_argument("--once", action="store_true", help="새 제출 한 번만 처리 후 종료")
    parser.add_argument("--weekly", action="store_true", help="주간 리포트 즉시 생성")
    parser.add_argument(
        "--monthly",
        nargs=3,
        metavar=("학생이름", "연도", "월"),
        help="월간 리포트 초안 생성 (예: --monthly 홍길동 2025 11)",
    )
    args = parser.parse_args()

    logger.info("=== 수학 과외 자동화 시스템 시작 ===")

    if not _check_config():
        logger.error(".env 파일 설정을 완료한 후 다시 실행해주세요.")
        sys.exit(1)

    # 공유 인스턴스 초기화
    db = Database()
    monitor = SheetsMonitor(db)
    grader = Grader()
    dup_checker = DuplicateChecker(db)
    notifiers = Notifiers()
    notion = NotionReporter()
    detector = AnomalyDetector()
    Path(config.DOWNLOAD_DIR).mkdir(exist_ok=True)

    if args.once:
        process_new_submissions(monitor, grader, dup_checker, notifiers, detector, db)
        return

    if args.weekly:
        run_weekly_report(monitor, grader, notifiers)
        return

    if args.monthly:
        student_name, year_str, month_str = args.monthly
        run_monthly_report(
            student_name, int(year_str), int(month_str),
            monitor, grader, notifiers, notion, db
        )
        return

    # 상시 실행 모드
    logger.info("폴링 간격: %d초 / 주간 리포트: 매주 일요일 오후 8시", config.POLLING_INTERVAL_SECONDS)

    schedule.every(config.POLLING_INTERVAL_SECONDS).seconds.do(
        process_new_submissions, monitor, grader, dup_checker, notifiers, detector, db
    )
    schedule.every().sunday.at("20:00").do(
        run_weekly_report, monitor, grader, notifiers
    )

    process_new_submissions(monitor, grader, dup_checker, notifiers, detector, db)

    while True:
        schedule.run_pending()
        time.sleep(5)


if __name__ == "__main__":
    main()
