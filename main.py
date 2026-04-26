"""
수학 과외 숙제 자동화 시스템 — 진입점

실행 방법:
  python main.py               # 상시 실행 (Sheets 폴링 + 스케줄)
  python main.py --once        # 새 제출 한 번만 처리 후 종료
  python main.py --scan-drive  # 학생 Drive 폴더 기존 파일 전부 채점
  python main.py --clear-records  # 제출기록 시트 전체 삭제 후 종료
  python main.py --weekly      # 주간 리포트 즉시 생성
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
from modules.anonymizer import Anonymizer
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


# 학생별 Drive 폴더 ID — .env 의 STUDENT_DRIVE_FOLDERS 에서 로드
STUDENT_DRIVE_FOLDERS = config.STUDENT_DRIVE_FOLDERS


# ────────────────────────────────────────────────────────────────────────────
# 핵심 공통 로직: 채점 → 저장 → Discord → 이상탐지
# ────────────────────────────────────────────────────────────────────────────

def _grade_files_and_notify(
    student: str,
    unit: str,
    grading_files: list[Path],
    monitor: SheetsMonitor,
    grader: Grader,
    notifiers: Notifiers,
    detector: AnomalyDetector,
    db: Database,
):
    """채점 → 오답노트/DB 저장 → Discord 알림 → 이상탐지 (전체 학생 대상)."""
    logger.info("채점 시작 — %s [%s], 파일 %d개", student, unit, len(grading_files))
    result = grader.grade_submission(grading_files, unit=unit)

    if not result.get("problems") and "error" in result:
        raise RuntimeError(f"채점 실패: {result['error']}")

    problems = result.get("problems", [])

    # Claude가 문제에서 추론한 단원 (없으면 폼 입력값 사용)
    effective_unit = result.get("inferred_unit") or unit

    # ⑤ 오답노트 저장 (Sheets — 오답만)
    monitor.append_wrong_answers(student, effective_unit, problems)

    # ⑤-b 제출기록 시트에 요약 저장
    monitor.write_submission_record(
        student, effective_unit,
        total_problems=result.get("total_problems", len(problems)),
        correct_count=result.get("correct_count", 0),
    )

    # ⑥ 세션 요약 저장 (SQLite — 이상탐지 피처)
    error_type_counts: dict[str, int] = {}
    for p in problems:
        if not p.get("is_correct") and p.get("error_type"):
            t = p["error_type"]
            error_type_counts[t] = error_type_counts.get(t, 0) + 1

    session_id = db.save_session(
        student_name=student,
        homework_title=effective_unit,
        submitted_at=datetime.now().strftime("%Y-%m-%d"),
        total_problems=result.get("total_problems", len(problems)),
        correct_count=result.get("correct_count", 0),
        error_type_counts=error_type_counts,
    )

    # ⑦ Discord 채점 완료 + 해설 (전체 학생)
    notifiers.discord_grading_with_explanation(student, effective_unit, result)

    # ⑦-b 숙제 추천 + 시험지 PDF 생성 + Discord 전송
    _generate_and_send_homework(student, unit, monitor, grader, notifiers)

    # ⑧ 이상탐지
    sessions = db.get_sessions(student)
    alerts = detector.detect(student, sessions)
    if alerts:
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


# ────────────────────────────────────────────────────────────────────────────
# 구글폼 제출 처리 (신규 제출 감지 시)
# ────────────────────────────────────────────────────────────────────────────

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
            db.mark_processed(row_num, student, "failed")
            notifiers.discord(f"❌ 처리 실패 — {student} / {homework}\n오류: {e}")

    if not found_new:
        logger.debug("새 제출 없음")


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

    # ① Drive 파일 다운로드
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
        if quality_score < config.MIN_IMAGE_QUALITY_SCORE:
            notifiers.discord_low_quality(student, processed_path.name, quality_score)
        grading_files.append(processed_path)

    # ④–⑧ 채점 + 저장 + Discord + 이상탐지
    _grade_files_and_notify(student, homework, grading_files, monitor, grader, notifiers, detector, db)
    logger.info("처리 완료 — %s", student)


# ────────────────────────────────────────────────────────────────────────────
# Drive 기존 파일 일괄 채점 (--scan-drive)
# ────────────────────────────────────────────────────────────────────────────

def scan_and_grade_drive_files(
    monitor: SheetsMonitor,
    grader: Grader,
    dup_checker: DuplicateChecker,
    notifiers: Notifiers,
    detector: AnomalyDetector,
    db: Database,
):
    """학생 Drive 폴더의 기존 파일을 전부 채점하여 오답노트 업데이트."""
    logger.info("=== Drive 일괄 채점 시작 ===")
    for student, folder_id in STUDENT_DRIVE_FOLDERS.items():
        logger.info("Drive 스캔 — %s (폴더: %s)", student, folder_id)

        # 단원별 파일 목록 (서브폴더명 = 단원명)
        file_groups = monitor.list_drive_folder_contents(folder_id)

        if not file_groups:
            logger.info("%s — Drive 파일 없음", student)
            continue

        for unit, file_infos in file_groups.items():
            # 다운로드
            downloaded: list[Path] = []
            for i, fi in enumerate(file_infos, start=1):
                path = monitor.download_drive_file(fi["id"], student, unit=unit, page=i)
                if path:
                    downloaded.append(path)

            if not downloaded:
                continue

            # 중복 제거
            valid_files: list[Path] = []
            for path in downloaded:
                is_dup, reason = dup_checker.is_duplicate(path, student)
                if is_dup:
                    logger.info("중복 제외: %s", path.name)
                else:
                    dup_checker.register(path, student)
                    valid_files.append(path)

            if not valid_files:
                logger.info("%s [%s] — 새 파일 없음 (모두 중복)", student, unit)
                continue

            # 이미지 전처리
            prepared = prepare_files_for_grading(valid_files)
            grading_files = [p for p, _ in prepared]

            try:
                _grade_files_and_notify(
                    student, unit, grading_files,
                    monitor, grader, notifiers, detector, db,
                )
            except Exception as e:
                logger.error("채점 실패 — %s [%s]: %s", student, unit, e)
                notifiers.discord(f"❌ Drive 채점 실패 — {student} / {unit}\n{e}")

    logger.info("=== Drive 일괄 채점 완료 ===")


# ────────────────────────────────────────────────────────────────────────────
# 숙제 추천 + PDF 생성
# ────────────────────────────────────────────────────────────────────────────

def _generate_and_send_homework(
    student: str,
    unit: str,
    monitor: SheetsMonitor,
    grader: Grader,
    notifiers: Notifiers,
):
    """오답 기반 숙제 추천 → 시험지/해설지 PDF → Discord + Drive."""
    try:
        import re as _re
        import anthropic as _anthropic

        wrong_history = monitor.get_wrong_answer_history(student)
        review_candidates = monitor.get_review_candidates(student, limit=2)

        client = _anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
        hw_resp = client.messages.create(
            model=config.CLAUDE_MODEL,
            max_tokens=800,
            system=HOMEWORK_SUGGESTION_SYSTEM,
            messages=[{"role": "user", "content": homework_suggestion_prompt(Anonymizer().mask(student), wrong_history, unit)}],
        )
        raw = hw_resp.content[0].text
        match = _re.search(r"\{.*\}", raw, _re.DOTALL)
        suggestion = grader._parse_json_response(raw) if match else {}

        if not suggestion.get("assignments"):
            logger.warning("숙제 추천 파싱 실패 — PDF 생성 건너뜀")
            return

        assignments = suggestion["assignments"]

        if review_candidates:
            types = ", ".join(set(r.get("오답유형", "") for r in review_candidates if r.get("오답유형")))
            assignments.append({
                "type": f"REVIEW — Previous errors ({types or 'mixed'})",
                "count": len(review_candidates),
                "difficulty": "Foundation",
                "note": "Based on recent mistakes — mark cao only",
            })

        notifiers.discord_homework_suggestion(student, suggestion)

        gen = ExamPDFGenerator()
        paths = gen.generate(student, unit, assignments)

        paper_url = monitor.upload_pdf_to_student_folder(
            paths["paper"], student, STUDENT_DRIVE_FOLDERS
        )
        notifiers.discord_exam_ready(student, unit, paths["paper"], paths["markscheme"], paper_url or "")

    except Exception as e:
        logger.error("숙제 PDF 생성 실패 — %s: %s", student, e, exc_info=True)
        notifiers.discord(f"⚠️ Homework PDF 생성 실패 — {student}\n{e}")


# ────────────────────────────────────────────────────────────────────────────
# 리포트
# ────────────────────────────────────────────────────────────────────────────

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


# ────────────────────────────────────────────────────────────────────────────
# 진입점
# ────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="수학 과외 숙제 자동화 시스템")
    parser.add_argument("--once", action="store_true", help="새 제출 한 번만 처리 후 종료")
    parser.add_argument("--scan-drive", action="store_true", help="학생 Drive 폴더 기존 파일 전부 채점")
    parser.add_argument("--clear-records", action="store_true", help="제출기록 시트 전체 삭제 후 종료")
    parser.add_argument("--weekly", action="store_true", help="주간 리포트 즉시 생성")
    parser.add_argument(
        "--monthly",
        nargs=3,
        metavar=("학생이름", "연도", "월"),
        help="월간 리포트 초안 생성 (예: --monthly 홍길동 2025 11)",
    )
    parser.add_argument(
        "--purge",
        type=int,
        metavar="일수",
        help="N일 이상 된 데이터 삭제 (예: --purge 365)",
    )
    parser.add_argument(
        "--delete-student",
        metavar="학생이름",
        help="특정 학생의 모든 데이터 삭제 (잊혀질 권리 대응)",
    )
    args = parser.parse_args()

    logger.info("=== 수학 과외 자동화 시스템 시작 ===")

    if not _check_config():
        logger.error(".env 파일 설정을 완료한 후 다시 실행해주세요.")
        sys.exit(1)

    db = Database()
    monitor = SheetsMonitor(db)
    grader = Grader()
    dup_checker = DuplicateChecker(db)
    notifiers = Notifiers()
    notion = NotionReporter()
    detector = AnomalyDetector()
    Path(config.DOWNLOAD_DIR).mkdir(exist_ok=True)

    if args.purge:
        result = db.purge_old_data(retention_days=args.purge)
        logger.info("데이터 정리 완료 (기준: %d일 이상): %s", args.purge, result)
        return

    if args.delete_student:
        result = db.delete_student_data(args.delete_student)
        logger.info("학생 데이터 삭제 완료 (%s): %s", args.delete_student, result)
        return

    if args.clear_records:
        monitor.clear_sheet(config.SUBMISSION_RECORD_SHEET)
        logger.info("제출기록 초기화 완료")
        return

    if args.scan_drive:
        scan_and_grade_drive_files(monitor, grader, dup_checker, notifiers, detector, db)
        return

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
