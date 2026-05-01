// ═══════════════════════════════════════════════════════════════
// 수학 과외 숙제 자동 채점 — Apps Script
//
// 동작: 구글폼 제출 → Claude로 채점 → 오답노트 시트에 저장 → Discord 알림
//
// 설정 순서 (한 번만):
//   1. 스크립트 속성에 ANTHROPIC_API_KEY, DISCORD_WEBHOOK_URL 추가
//   2. testDiscord()  → Discord에 테스트 메시지 오는지 확인
//   3. setupSheets()  → 오답노트 헤더 9컬럼으로 설정
//   4. setupTrigger() → 폼 제출 + 주간 리포트 트리거 자동 설치
//   5. 폼에 실제 제출하면 자동 처리됨
//
// 디버깅 / 수동 실행:
//   - processLatestRow() : 트리거 없이 마지막 폼 응답 행을 수동 재처리
//   - weeklyReport()     : 주간 리포트 즉시 생성
//   - 실행 로그(보기 → 실행) 에서 단계별 진행 확인
// ═══════════════════════════════════════════════════════════════

const FORM_RESPONSE_SHEET = '설문지 응답 시트1';
const WRONG_ANSWER_SHEET  = '오답노트';
const CLAUDE_MODEL        = 'claude-opus-4-5';

// 오답노트 헤더 — setupSheets() 가 이 순서대로 1행에 씁니다
const WRONG_ANSWER_HEADERS = ['학생', '단원', '날짜', '문제번호', '학생답안', '정답', '오답유형', 'AI해설', '복습완료'];

// 폼 응답 시트의 열 인덱스 (1-based) — 시트 구조 바뀌면 여기만 수정
const COL = {
  TIMESTAMP: 1,  // A: 타임스탬프
  STUDENT:   2,  // B: 학생 이름
  FILES:     3,  // C: 숙제 업로드 (Drive URL)
  UNIT:      6,  // F: 단원명
};

// ═══════════════════════════════════════════════════════════════
// 0. 설정 헬퍼
// ═══════════════════════════════════════════════════════════════
function getProp_(key) {
  const v = PropertiesService.getScriptProperties().getProperty(key);
  if (!v) throw new Error(`스크립트 속성 ${key} 가 비어있어요. 프로젝트 설정 → 스크립트 속성에서 추가해주세요.`);
  return v;
}

// ═══════════════════════════════════════════════════════════════
// 1. Discord 테스트 — 첫 설정 후 실행해서 웹훅이 살아있는지 확인
// ═══════════════════════════════════════════════════════════════
function testDiscord() {
  sendDiscord_('✅ Apps Script → Discord 연결 성공! 이 메시지가 보이면 웹훅 설정 완료에요.');
  Logger.log('Discord 테스트 메시지 전송 완료. Discord 채널을 확인해주세요.');
}

// ═══════════════════════════════════════════════════════════════
// 2. 오답노트 헤더 설정 — 한 번만 실행 (또는 헤더 깨졌을 때)
// ═══════════════════════════════════════════════════════════════
function setupSheets() {
  const sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(WRONG_ANSWER_SHEET);
  if (!sheet) throw new Error(`시트 "${WRONG_ANSWER_SHEET}" 가 없어요. 시트 탭을 먼저 만들어주세요.`);

  sheet.getRange(1, 1, 1, WRONG_ANSWER_HEADERS.length)
    .setValues([WRONG_ANSWER_HEADERS])
    .setFontWeight('bold');
  sheet.setFrozenRows(1);

  Logger.log('오답노트 헤더 설정 완료: ' + WRONG_ANSWER_HEADERS.join(' / '));
}

// ═══════════════════════════════════════════════════════════════
// 3. 트리거 자동 설치 — 한 번만 실행
//    - onFormSubmit: 폼 제출 시 자동 채점
//    - weeklyReport: 매주 일요일 저녁 8시 주간 리포트
// ═══════════════════════════════════════════════════════════════
function setupTrigger() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();

  // 기존 트리거 제거 (중복 방지)
  ScriptApp.getProjectTriggers()
    .filter(t => ['onFormSubmit', 'weeklyReport'].indexOf(t.getHandlerFunction()) !== -1)
    .forEach(t => ScriptApp.deleteTrigger(t));

  // 폼 제출 트리거
  ScriptApp.newTrigger('onFormSubmit').forSpreadsheet(ss).onFormSubmit().create();

  // 주간 리포트 — 일요일 20시
  ScriptApp.newTrigger('weeklyReport')
    .timeBased()
    .onWeekDay(ScriptApp.WeekDay.SUNDAY)
    .atHour(20)
    .create();

  Logger.log('트리거 설치 완료: onFormSubmit (폼 제출), weeklyReport (일요일 20시)');
  sendDiscord_('🔧 트리거 설치 완료\n• 폼 제출 시 자동 채점\n• 매주 일요일 저녁 8시 주간 리포트');
}

// ═══════════════════════════════════════════════════════════════
// 3. 메인 — 폼 제출 시 자동 실행
// ═══════════════════════════════════════════════════════════════
function onFormSubmit(e) {
  try {
    let sheet, row;
    if (e && e.range) {
      sheet = e.range.getSheet();
      row   = e.range.getRow();
      Logger.log(`폼 제출 감지: 시트=${sheet.getName()}, 행=${row}`);
    } else {
      // 에디터에서 수동 실행한 경우 — 마지막 폼 행으로 폴백
      sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(FORM_RESPONSE_SHEET);
      if (!sheet) throw new Error(`시트 "${FORM_RESPONSE_SHEET}" 없음`);
      row = sheet.getLastRow();
      if (row < 2) throw new Error('처리할 폼 응답이 없어요.');
      Logger.log(`수동 실행 → 마지막 행(${row}) 처리`);
    }
    processRow_(sheet, row);
  } catch (err) {
    Logger.log('onFormSubmit 오류: ' + err.stack);
    try { sendDiscord_(`❌ 자동 채점 실패\n오류: ${err.message}`); } catch (_) {}
  }
}

// 트리거 없이 마지막 행을 수동으로 재처리 — 디버깅/재실행용
function processLatestRow() {
  const sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(FORM_RESPONSE_SHEET);
  if (!sheet) throw new Error(`시트 "${FORM_RESPONSE_SHEET}" 를 찾을 수 없어요.`);
  const row = sheet.getLastRow();
  if (row < 2) throw new Error('처리할 폼 응답이 없어요.');
  Logger.log(`마지막 행 수동 처리: ${row}`);
  processRow_(sheet, row);
}

// ═══════════════════════════════════════════════════════════════
// 4. 핵심 로직 — 한 행 처리
// ═══════════════════════════════════════════════════════════════
function processRow_(sheet, row) {
  const values = sheet.getRange(row, 1, 1, sheet.getLastColumn()).getValues()[0];
  const student = String(values[COL.STUDENT - 1] || '').trim();
  const unit    = String(values[COL.UNIT    - 1] || '').trim();
  const filesRaw = String(values[COL.FILES   - 1] || '').trim();

  if (!student) { Logger.log('학생 이름 없음 → 건너뜀'); return; }
  if (!filesRaw) { Logger.log('파일 없음 → 건너뜀'); return; }

  const fileIds = extractFileIds_(filesRaw);
  Logger.log(`학생=${student}, 단원=${unit}, 파일수=${fileIds.length}`);

  if (fileIds.length === 0) {
    sendDiscord_(`⚠️ ${student} — 업로드 링크에서 파일을 못 찾았어요.`);
    return;
  }

  sendDiscord_(`🔄 채점 시작 — ${student} / ${unit || '단원 미기재'} (파일 ${fileIds.length}개)`);

  const result = gradeWithClaude_(fileIds, unit);
  saveWrongAnswers_(student, unit, result);
  sendGradingEmbed_(student, unit, result);

  Logger.log(`채점 완료 — ${student}: ${result.correct_count}/${result.total_problems}`);
}

// ═══════════════════════════════════════════════════════════════
// 5. Drive 파일 ID 추출 — URL/ID/콤마 구분 모두 지원
// ═══════════════════════════════════════════════════════════════
function extractFileIds_(raw) {
  const tokens = raw.split(/[\s,]+/).filter(Boolean);
  const ids = [];
  for (const t of tokens) {
    // /d/{id} 또는 ?id={id} 또는 그냥 {id}
    const m = t.match(/[-\w]{25,}/);
    if (m) ids.push(m[0]);
  }
  return ids;
}

// ═══════════════════════════════════════════════════════════════
// 6. Claude Vision 채점
// ═══════════════════════════════════════════════════════════════
function gradeWithClaude_(fileIds, unit) {
  const apiKey = getProp_('ANTHROPIC_API_KEY');
  const content = [];

  for (const id of fileIds) {
    try {
      const blob = DriveApp.getFileById(id).getBlob();
      const mime = blob.getContentType();
      const data = Utilities.base64Encode(blob.getBytes());

      if (mime === 'application/pdf') {
        content.push({ type: 'document', source: { type: 'base64', media_type: mime, data } });
      } else if (mime && mime.indexOf('image/') === 0) {
        content.push({ type: 'image', source: { type: 'base64', media_type: mime, data } });
      } else {
        Logger.log(`지원하지 않는 파일 형식 (${mime}) → 건너뜀: ${id}`);
      }
    } catch (err) {
      Logger.log(`파일 로드 실패 ${id}: ${err}`);
    }
  }

  if (content.length === 0) throw new Error('처리 가능한 파일이 없어요. (Drive 권한 또는 파일 형식 확인)');

  content.push({ type: 'text', text: unit ? `${GRADING_PROMPT}\n\n학생이 입력한 단원명: ${unit}` : GRADING_PROMPT });

  const res = UrlFetchApp.fetch('https://api.anthropic.com/v1/messages', {
    method: 'post',
    contentType: 'application/json',
    headers: {
      'x-api-key': apiKey,
      'anthropic-version': '2023-06-01',
    },
    payload: JSON.stringify({
      model: CLAUDE_MODEL,
      max_tokens: 4096,
      system: GRADING_SYSTEM,
      messages: [{ role: 'user', content }],
    }),
    muteHttpExceptions: true,
  });

  const code = res.getResponseCode();
  const body = res.getContentText();
  if (code !== 200) throw new Error(`Claude API 오류 (${code}): ${body.slice(0, 300)}`);

  const json = JSON.parse(body);
  const text = json.content && json.content[0] && json.content[0].text;
  if (!text) throw new Error('Claude 응답이 비어있어요: ' + body.slice(0, 300));

  return parseJson_(text);
}

function parseJson_(text) {
  // 1. 코드 펜스 제거
  let s = text.trim()
    .replace(/^```(?:json)?\s*/i, '')
    .replace(/\s*```$/i, '')
    .trim();

  // 2. 첫 { ~ 마지막 } 추출 (앞뒤 잡설 제거)
  const first = s.indexOf('{');
  const last  = s.lastIndexOf('}');
  if (first !== -1 && last !== -1 && last > first) s = s.slice(first, last + 1);

  // 3. 그대로 시도
  try { return JSON.parse(s); } catch (_) {}

  // 4. 문자열 안의 raw 제어문자(줄바꿈/탭) 를 escape 시퀀스로 변환
  //    JSON 스펙상 문자열 안에서는 \n/\t/\r 가 escape 되어야 하는데
  //    Claude가 종종 raw 로 넣어서 깨짐
  try { return JSON.parse(repairJsonStrings_(s)); } catch (_) {}

  // 5. 백슬래시 보정 (LaTeX \frac 등) 까지 추가
  try {
    const repaired = repairJsonStrings_(s).replace(/\\(?!["\\\/bfnrtu])/g, '\\\\');
    return JSON.parse(repaired);
  } catch (err) {
    Logger.log('JSON 파싱 최종 실패: ' + err + '\n원본 응답 앞 1500자:\n' + text.slice(0, 1500));
    return { problems: [], total_problems: 0, correct_count: 0, overall_feedback: '(JSON 파싱 실패 — 실행 로그 확인)' };
  }
}

// JSON 문자열 리터럴 안의 raw 제어문자만 escape — 구조적 줄바꿈은 그대로
function repairJsonStrings_(s) {
  let out = '';
  let inString = false;
  let escaped = false;
  for (let i = 0; i < s.length; i++) {
    const c = s[i];
    if (escaped) { out += c; escaped = false; continue; }
    if (c === '\\') { out += c; escaped = true; continue; }
    if (c === '"')  { out += c; inString = !inString; continue; }
    if (inString) {
      if (c === '\n') { out += '\\n'; continue; }
      if (c === '\r') { out += '\\r'; continue; }
      if (c === '\t') { out += '\\t'; continue; }
    }
    out += c;
  }
  return out;
}

// ═══════════════════════════════════════════════════════════════
// 7. 오답노트 시트 저장 (오답만, 문제별로 한 행씩)
// 열: 학생 / 단원 / 날짜 / 문제번호 / 학생답안 / 정답 / 오답유형 / AI해설 / 복습완료
// ═══════════════════════════════════════════════════════════════
function saveWrongAnswers_(student, unit, result) {
  const sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(WRONG_ANSWER_SHEET);
  if (!sheet) { Logger.log(`시트 "${WRONG_ANSWER_SHEET}" 없음 → 저장 건너뜀`); return; }

  const displayUnit = result.inferred_unit || unit || '미기재';
  const date = Utilities.formatDate(new Date(), Session.getScriptTimeZone(), 'yyyy-MM-dd');

  const rows = (result.problems || [])
    .filter(p => !p.is_correct)
    .map(p => [
      student,
      displayUnit,
      date,
      p.problem_number || '',
      p.student_answer || '',
      p.correct_answer || '',
      p.error_type     || '',
      p.feedback       || '',
      '',  // 복습완료 — 학생/선생님이 수동 체크
    ]);

  if (rows.length > 0) {
    sheet.getRange(sheet.getLastRow() + 1, 1, rows.length, WRONG_ANSWER_HEADERS.length).setValues(rows);
    Logger.log(`오답노트에 ${rows.length}행 추가 (${student} / ${displayUnit} / ${date})`);
  } else {
    Logger.log('오답 없음 → 오답노트 추가 안 함');
  }
}

// ═══════════════════════════════════════════════════════════════
// 8. 주간 리포트 — 매주 일요일 20시 자동 실행 (트리거)
//    수동 실행: 함수 드롭다운에서 weeklyReport 선택 → 실행
// ═══════════════════════════════════════════════════════════════
function weeklyReport() {
  const sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(WRONG_ANSWER_SHEET);
  if (!sheet || sheet.getLastRow() < 2) {
    sendDiscord_('📊 주간 리포트 — 등록된 오답이 없어요.');
    return;
  }

  const lastCol = WRONG_ANSWER_HEADERS.length;
  const data = sheet.getRange(2, 1, sheet.getLastRow() - 1, lastCol).getValues();

  const tz = Session.getScriptTimeZone();
  const today   = new Date();
  const weekAgo = new Date(today.getTime() - 7 * 24 * 60 * 60 * 1000);

  // 학생별 집계
  const byStudent = {};
  for (const r of data) {
    const student = r[0];
    const unit    = r[1];
    const dateStr = r[2];
    const errType = r[6];
    if (!student || !dateStr) continue;

    const d = new Date(dateStr);
    if (isNaN(d.getTime()) || d < weekAgo) continue;

    if (!byStudent[student]) byStudent[student] = { count: 0, types: {}, units: {} };
    byStudent[student].count++;
    if (unit)    byStudent[student].units[unit]    = (byStudent[student].units[unit]    || 0) + 1;
    if (errType) byStudent[student].types[errType] = (byStudent[student].types[errType] || 0) + 1;
  }

  const fmt = d => Utilities.formatDate(d, tz, 'M/d');
  const range = `${fmt(weekAgo)} ~ ${fmt(today)}`;

  if (Object.keys(byStudent).length === 0) {
    sendDiscord_(`📊 **주간 리포트** (${range})\n이번 주 등록된 오답이 없어요.`);
    return;
  }

  const lines = [`📊 **주간 리포트** (${range})\n`];
  for (const [student, s] of Object.entries(byStudent)) {
    const topType = Object.entries(s.types).sort((a, b) => b[1] - a[1])[0];
    const typeStr = topType ? `${topType[0]} ${topType[1]}건` : '없음';
    const units   = Object.keys(s.units).slice(0, 3).join(', ') || '—';
    lines.push(`• **${student}** — 오답 ${s.count}건 / 단원: ${units} / 자주 틀린 유형: ${typeStr}`);
  }

  sendDiscord_(lines.join('\n'));
  Logger.log(`주간 리포트 전송 완료 — 학생 ${Object.keys(byStudent).length}명`);
}

// ═══════════════════════════════════════════════════════════════
// 9. Discord 알림
// ═══════════════════════════════════════════════════════════════
function sendDiscord_(text) {
  const url = getProp_('DISCORD_WEBHOOK_URL');
  const res = UrlFetchApp.fetch(url, {
    method: 'post',
    contentType: 'application/json',
    payload: JSON.stringify({ content: text }),
    muteHttpExceptions: true,
  });
  const code = res.getResponseCode();
  if (code >= 300) {
    Logger.log(`Discord 텍스트 전송 실패 (${code}): ${res.getContentText().slice(0, 300)}`);
  }
}

function sendGradingEmbed_(student, unit, result) {
  const url = getProp_('DISCORD_WEBHOOK_URL');
  const total   = result.total_problems || 0;
  const correct = result.correct_count  || 0;
  const wrong   = total - correct;
  const pct     = total > 0 ? Math.round(correct / total * 100) : 0;
  const color   = pct >= 80 ? 5763719 : pct >= 60 ? 16776960 : 15548997;

  const typeCounts = {};
  for (const p of (result.problems || [])) {
    if (!p.is_correct && p.error_type) {
      typeCounts[p.error_type] = (typeCounts[p.error_type] || 0) + 1;
    }
  }
  const typeStr = Object.entries(typeCounts).map(([k, v]) => `${k} ${v}`).join(' / ') || '없음';
  const displayUnit = result.inferred_unit || unit || '미기재';
  // Discord embed 필드는 1024자 제한 — 넘치면 잘라야 embed 자체가 안 깨짐
  const overall = (result.overall_feedback || '—').toString().slice(0, 1000);

  const embed = {
    title: `✅ 채점 완료 — ${student}`,
    color,
    fields: [
      { name: '단원',      value: displayUnit,                      inline: true  },
      { name: '점수',      value: `${correct}/${total} (${pct}%)`,  inline: true  },
      { name: '오답',      value: `${wrong}건`,                     inline: true  },
      { name: '오답 유형', value: typeStr,                          inline: false },
      { name: '종합 피드백', value: overall,                        inline: false },
    ],
  };

  const res = UrlFetchApp.fetch(url, {
    method: 'post',
    contentType: 'application/json',
    payload: JSON.stringify({ embeds: [embed] }),
    muteHttpExceptions: true,
  });
  const code = res.getResponseCode();
  if (code >= 300) {
    Logger.log(`Discord embed 전송 실패 (${code}): ${res.getContentText().slice(0, 500)}`);
    // embed 가 거절되면 텍스트로라도 알림
    sendDiscord_(`✅ 채점 완료 — ${student} | ${displayUnit} | ${correct}/${total} (${pct}%)`);
  }

  // 틀린 문제 상세
  const wrongList = (result.problems || []).filter(p => !p.is_correct);
  if (wrongList.length > 0) {
    const lines = wrongList.map(p => {
      const num = p.problem_number || '?';
      const sa = p.student_answer ? `학생: ${p.student_answer}` : '';
      const ca = p.correct_answer ? `정답: ${p.correct_answer}` : '';
      const ans = [sa, ca].filter(Boolean).join(' → ');
      return `**${num}번**${ans ? ` | ${ans}` : ''}\n${p.feedback || ''}`;
    });
    // Discord 메시지는 2000자 제한 — 청크로 나눠 전송
    let buf = `📝 **틀린 문제 해설**\n\n`;
    for (const line of lines) {
      if (buf.length + line.length + 2 > 1900) {
        sendDiscord_(buf);
        buf = '';
      }
      buf += line + '\n\n';
    }
    if (buf.trim()) sendDiscord_(buf);
  }
}

// ═══════════════════════════════════════════════════════════════
// 9. 채점 프롬프트
// ═══════════════════════════════════════════════════════════════
const GRADING_SYSTEM = `당신은 수학 과외 선생님의 숙제 채점 도우미입니다.
학생이 제출한 숙제 사진/PDF를 분석하여 정확하고 친절한 피드백을 제공합니다.

응답은 반드시 순수 JSON 객체 하나만 출력하세요. 다음 규칙을 절대 어기지 마세요:
- 마크다운 코드블록(\`\`\`json) 으로 감싸지 마세요. { 로 시작해서 } 로 끝나야 합니다.
- 모든 문자열 값은 한 줄로 작성하세요. 줄바꿈, 탭 문자를 절대 넣지 마세요.
- 문자열 안에 큰따옴표(") 를 쓰지 마세요. 인용이 필요하면 작은따옴표(') 또는 「」 를 쓰세요.
- 백슬래시(\\) 를 쓸 때는 반드시 \\\\ 로 이스케이프하세요. (LaTeX 수식은 쓰지 말고 일반 글로 풀어 설명하세요.)
- feedback 은 짧고 간결하게 한 문장으로 (가능하면 80자 이내).`;

const GRADING_PROMPT = `다음 숙제 이미지/PDF를 분석해서 아래 JSON 형식으로만 응답해주세요.

분석 항목:
1. 이미지의 모든 문제를 빠짐없이 (1번 아래 a/b/c 소문제도 각각)
2. 학생이 실제로 쓴 답을 읽어서 정답과 비교
3. 오답이면 유형 분류: 개념부족 / 계산실수 / 풀이순서 / 문제이해 / 기타
4. 학생 눈높이에 맞춘 구체적 피드백
5. 문제 내용 보고 단원 추정 (사인 법칙, 조건부 확률 등)

응답 형식:
{
  "inferred_unit": "추정 단원명",
  "total_problems": 0,
  "correct_count": 0,
  "overall_feedback": "한 줄 종합",
  "problems": [
    {
      "problem_number": "1a",
      "is_correct": true,
      "student_answer": "...",
      "correct_answer": "...",
      "error_type": null,
      "feedback": "..."
    }
  ]
}`;
