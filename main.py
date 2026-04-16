"""
수학 과외 숙제 자동화 시스템 — 진입점

실행 방법:
  python main.py          # 상시 실행 (Sheets 폴링 + 스케줄)
  python main.py --once   # 새 제출 한 번만 처리 후 종료
  python main.py --weekly # 주간 리포트 즉시 생성
  python main.py --monthly 홍길동 2025 11  # 특정 학생 월간 리포트 초안 생성
"""

import argparse
import logging
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import schedule

import config
from modules.duplicate_checker import DuplicateChecker
from modules.grader import Grader
from modules.image_processor import prepare_files_for_grading
from modules.notifiers import Notifiers
from modules.notion_reporter import NotionReporter
from modules.sheets_monitor import SheetsMonitor

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("tutoring_automation.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)


def process_new_submissions(
    monitor: SheetsMonitor,
    grader: Grader,
    dup_checker: DuplicateChecker,
    notifiers: Notifiers,
):
    """새 폼 제출을 처리하는 메인 루프 1회 실행."""
    found_new = False

    for submission in monitor.get_new_submissions():
        found_new = True
        student = submission["student_name"]
        homework = submission["homework_title"]
        row_num = submission["row_number"]
        logger.info("새 제출 감지 — %s: %s (행 %d)", student, homework, row_num)

        # ① Drive 파일 다운로드
        downloaded: list[Path] = []
        for file_id in submission["file_links"]:
            filename = f"{student}_{homework}_{file_id[:8]}"
            path = monitor.download_drive_file(file_id, filename)
            if path:
                downloaded.append(path)

        if not downloaded:
            logger.warning("다운로드된 파일 없음 — 행 %d 건너뜀", row_num)
            monitor.mark_processed(row_num)
            continue

        # ② 중복 검사
        valid_files: list[Path] = []
        for path in downloaded:
            is_dup, reason = dup_checker.is_duplicate(path, student)
            if is_dup:
                logger.info("중복 파일 제외: %s — %s", path.name, reason)
                notifiers.discord_duplicate_detected(student, path.name, reason)
            else:
                dup_checker.register(path, student)
                valid_files.append(path)

        if not valid_files:
            logger.info("유효한 파일 없음 (모두 중복) — 행 %d", row_num)
            monitor.mark_processed(row_num)
            continue

        # ③ 이미지 전처리 + 품질 확인
        prepared = prepare_files_for_grading(valid_files)
        grading_files: list[Path] = []
        for processed_path, quality_score in prepared:
            if quality_score < config.MIN_IMAGE_QUALITY_SCORE:
                logger.warning("품질 낮음: %s (점수: %s)", processed_path.name, quality_score)
                notifiers.discord_low_quality(student, processed_path.name, quality_score)
            grading_files.append(processed_path)

        # ④ Claude Vision 채점
        logger.info("채점 시작 — %s, 파일 %d개", student, len(grading_files))
        result = grader.grade_submission(grading_files)

        if "error" in result and not result.get("problems"):
            logger.error("채점 실패: %s", result.get("error"))
            monitor.mark_processed(row_num)
            continue

        # ⑤ 오답노트 저장
        monitor.append_wrong_answers(student, homework, result.get("problems", []))

        # ⑥ Discord 채점 완료 알림
        notifiers.discord_grading_complete(student, homework, result)

        # ⑦ 누적 패턴 분석 (3회 연속 같은 유형이면 Discord 추가 알림)
        history = monitor.get_wrong_answer_history(student)
        pattern = grader.analyze_patterns(student, history)
        if pattern.get("consecutive_same_error"):
            notifiers.discord(
                f"🔁 **반복 오류 감지** — {student}\n"
                f"패턴: {pattern.get('pattern_summary', '')}\n"
                f"다음 수업 포인트: {', '.join(pattern.get('next_lesson_focus', []))}"
            )

        monitor.mark_processed(row_num)
        logger.info("처리 완료 — %s 행 %d", student, row_num)

    if not found_new:
        logger.debug("새 제출 없음")


def run_weekly_report(monitor: SheetsMonitor, grader: Grader, notifiers: Notifiers):
    """주간 리포트 생성 및 Discord 전송."""
    week_start = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
    logger.info("주간 리포트 생성 중 (%s 이후)...", week_start)

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
):
    """특정 학생의 월간 리포트 초안 생성 후 Notion 저장."""
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

    # 초기화
    logger.info("=== 수학 과외 자동화 시스템 시작 ===")
    monitor = SheetsMonitor()
    grader = Grader()
    dup_checker = DuplicateChecker(config.DUPLICATE_HASHES_FILE)
    notifiers = Notifiers()
    notion = NotionReporter()

    if args.once:
        process_new_submissions(monitor, grader, dup_checker, notifiers)
        return

    if args.weekly:
        run_weekly_report(monitor, grader, notifiers)
        return

    if args.monthly:
        student_name, year_str, month_str = args.monthly
        run_monthly_report(
            student_name, int(year_str), int(month_str),
            monitor, grader, notifiers, notion
        )
        return

    # 상시 실행 모드
    logger.info("폴링 간격: %d초 / 주간 리포트: 매주 일요일 오후 8시", config.POLLING_INTERVAL_SECONDS)

    # 스케줄 등록
    schedule.every(config.POLLING_INTERVAL_SECONDS).seconds.do(
        process_new_submissions, monitor, grader, dup_checker, notifiers
    )
    schedule.every().sunday.at("20:00").do(
        run_weekly_report, monitor, grader, notifiers
    )

    # 시작 즉시 한 번 실행
    process_new_submissions(monitor, grader, dup_checker, notifiers)

    while True:
        schedule.run_pending()
        time.sleep(5)


if __name__ == "__main__":
    main()
