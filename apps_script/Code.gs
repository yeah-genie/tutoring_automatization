// ═══════════════════════════════════════════════════════════════
// 수학 과외 숙제 자동 채점 — Apps Script
//
// 동작: 구글폼 제출 → Claude로 채점 → 오답노트 시트에 저장 → Discord 알림
//
// 설정 순서 (한 번만):
//   1. 스크립트 속성에 ANTHROPIC_API_KEY, DISCORD_WEBHOOK_URL 추가
//   2. testDiscord() 실행 → Discord에 테스트 메시지 오는지 확인
//   3. setupTrigger() 실행 → 폼 제출 트리거 자동 설치
//   4. 폼에 실제 제출하면 자동 처리됨
//
// 디버깅:
//   - processLatestRow() : 트리거 없이 마지막 폼 응답 행을 수동 재처리
//   - 실행 로그(보기 → 실행) 에서 단계별 진행 확인
// ═══════════════════════════════════════════════════════════════

const FORM_RESPONSE_SHEET = '설문지 응답 시트1';
const WRONG_ANSWER_SHEET  = '오답노트';
const CLAUDE_MODEL        = 'claude-opus-4-5';

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
// 2. 트리거 자동 설치 — 한 번만 실행
// ═══════════════════════════════════════════════════════════════
function setupTrigger() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();

  // 기존 onFormSubmit 트리거 제거 (중복 방지)
  ScriptApp.getProjectTriggers()
    .filter(t => t.getHandlerFunction() === 'onFormSubmit')
    .forEach(t => ScriptApp.deleteTrigger(t));

  // 새 트리거 설치
  ScriptApp.newTrigger('onFormSubmit')
    .forSpreadsheet(ss)
    .onFormSubmit()
    .create();

  Logger.log('폼 제출 트리거 설치 완료. 이제 폼에 제출하면 자동 채점돼요.');
  sendDiscord_('🔧 폼 제출 트리거 설치 완료. 이제 폼 제출 시 자동 채점됩니다.');
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
  saveWrongAnswers_(student, result);
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
  const m = text.match(/\{[\s\S]*\}/);
  try {
    return JSON.parse(m ? m[0] : text);
  } catch (_) {
    return { problems: [], total_problems: 0, correct_count: 0, overall_feedback: text.slice(0, 200) };
  }
}

// ═══════════════════════════════════════════════════════════════
// 7. 오답노트 시트 저장 (오답만)
// 열: 학생이름 / 문제번호 / 정답여부 / 오답유형 / 첨삭자 / AI해설
// ═══════════════════════════════════════════════════════════════
function saveWrongAnswers_(student, result) {
  const sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(WRONG_ANSWER_SHEET);
  if (!sheet) { Logger.log(`시트 "${WRONG_ANSWER_SHEET}" 없음 → 저장 건너뜀`); return; }

  const rows = (result.problems || [])
    .filter(p => !p.is_correct)
    .map(p => [
      student,
      p.problem_number || '',
      'X',
      p.error_type || '',
      'AI',
      p.feedback || '',
    ]);

  if (rows.length > 0) {
    sheet.getRange(sheet.getLastRow() + 1, 1, rows.length, 6).setValues(rows);
    Logger.log(`오답노트에 ${rows.length}행 추가`);
  }
}

// ═══════════════════════════════════════════════════════════════
// 8. Discord 알림
// ═══════════════════════════════════════════════════════════════
function sendDiscord_(text) {
  const url = getProp_('DISCORD_WEBHOOK_URL');
  UrlFetchApp.fetch(url, {
    method: 'post',
    contentType: 'application/json',
    payload: JSON.stringify({ content: text }),
    muteHttpExceptions: true,
  });
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

  const embed = {
    title: `✅ 채점 완료 — ${student}`,
    color,
    fields: [
      { name: '단원',      value: displayUnit,                      inline: true  },
      { name: '점수',      value: `${correct}/${total} (${pct}%)`,  inline: true  },
      { name: '오답',      value: `${wrong}건`,                     inline: true  },
      { name: '오답 유형', value: typeStr,                          inline: false },
      { name: '종합 피드백', value: result.overall_feedback || '—', inline: false },
    ],
  };

  UrlFetchApp.fetch(url, {
    method: 'post',
    contentType: 'application/json',
    payload: JSON.stringify({ embeds: [embed] }),
    muteHttpExceptions: true,
  });

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
반드시 JSON 형식으로만 응답하고, JSON 외 다른 텍스트는 포함하지 마세요.`;

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
