// ═══════════════════════════════════════════════════════════════
// 수학 과외 숙제 자동 채점 시스템 — Google Apps Script
// 스프레드시트에 연결해서 폼 제출 시 자동 실행됩니다.
// ═══════════════════════════════════════════════════════════════

// ─── API 키 (Script Properties에서 읽어옴 — 코드에 직접 넣지 마세요) ──
// Apps Script 에디터 → 프로젝트 설정 → 스크립트 속성에서 추가하세요.
const ANTHROPIC_API_KEY  = PropertiesService.getScriptProperties().getProperty('ANTHROPIC_API_KEY');
const DISCORD_WEBHOOK_URL = PropertiesService.getScriptProperties().getProperty('DISCORD_WEBHOOK_URL');
const WRONG_ANSWER_SHEET = '오답노트';
const CLAUDE_MODEL = 'claude-opus-4-7';

// ─── 폼 질문 제목 (실제 폼과 일치해야 함) ────────────────────────
const FORM_FIELDS = {
  student: '학생',
  files:   '숙제 업로드',
  unit:    '단원명',
};

// ═══════════════════════════════════════════════════════════════
// 메인 함수 — 폼 제출 시 자동 실행
// ═══════════════════════════════════════════════════════════════
function onFormSubmit(e) {
  try {
    const sub = parseFormResponse(e);
    if (!sub) return;

    // 중복 파일 제거
    const newIds = filterDuplicates(sub.fileIds);
    if (newIds.length === 0) {
      sendDiscord(`⚠️ **중복 파일** — ${sub.studentName}\n이미 처리된 파일이에요.`);
      return;
    }

    // Claude로 채점
    sendDiscord(`🔄 **채점 시작** — ${sub.studentName} / ${sub.unitName || '단원 미기재'}\n파일 ${newIds.length}개 처리 중...`);
    const result = gradeWithClaude(newIds);

    // 오답노트 저장
    saveToSheet(sub.studentName, sub.unitName, result);

    // Discord 채점 결과 전송
    sendGradingEmbed(sub.studentName, sub.unitName, result);

  } catch (err) {
    Logger.log(err.toString());
    sendDiscord(`❌ **오류 발생**\n${err.message}`);
  }
}

// ═══════════════════════════════════════════════════════════════
// 폼 응답 파싱
// ═══════════════════════════════════════════════════════════════
function parseFormResponse(e) {
  const responses = e.response.getItemResponses();
  const data = { studentName: '', unitName: '', fileIds: [] };

  for (const r of responses) {
    const title = r.getItem().getTitle();
    const val   = r.getResponse();

    if (title === FORM_FIELDS.student) {
      data.studentName = val.toString().trim();
    } else if (title === FORM_FIELDS.unit) {
      data.unitName = val.toString().trim();
    } else if (title === FORM_FIELDS.files) {
      // 구글폼 파일 업로드: Drive 파일 ID 배열 반환
      data.fileIds = Array.isArray(val) ? val : [val];
    }
  }

  return data.studentName ? data : null;
}

// ═══════════════════════════════════════════════════════════════
// 중복 파일 감지 (Drive 파일 ID 기반)
// ═══════════════════════════════════════════════════════════════
function filterDuplicates(fileIds) {
  const props  = PropertiesService.getScriptProperties();
  const seen   = JSON.parse(props.getProperty('seenFileIds') || '[]');
  const newIds = fileIds.filter(id => id && !seen.includes(id));

  if (newIds.length > 0) {
    props.setProperty('seenFileIds', JSON.stringify([...seen, ...newIds]));
  }
  return newIds;
}

// ═══════════════════════════════════════════════════════════════
// Claude Vision 채점
// ═══════════════════════════════════════════════════════════════
function gradeWithClaude(fileIds) {
  const content = [];

  for (const fileId of fileIds) {
    try {
      const file     = DriveApp.getFileById(fileId);
      const blob     = file.getBlob();
      const mime     = blob.getContentType();
      const base64   = Utilities.base64Encode(blob.getBytes());

      if (mime === 'application/pdf') {
        content.push({
          type: 'document',
          source: { type: 'base64', media_type: 'application/pdf', data: base64 },
        });
      } else {
        // image/jpeg, image/png 등
        content.push({
          type: 'image',
          source: { type: 'base64', media_type: mime, data: base64 },
        });
      }
    } catch (err) {
      Logger.log(`파일 로드 실패 (${fileId}): ${err}`);
    }
  }

  if (content.length === 0) throw new Error('처리 가능한 파일이 없습니다.');

  content.push({ type: 'text', text: GRADING_PROMPT });

  const res = UrlFetchApp.fetch('https://api.anthropic.com/v1/messages', {
    method: 'post',
    headers: {
      'x-api-key':          ANTHROPIC_API_KEY,
      'anthropic-version':  '2023-06-01',
      'content-type':       'application/json',
      'anthropic-beta':     'pdfs-2024-09-25',  // PDF 지원 활성화
    },
    payload: JSON.stringify({
      model:      CLAUDE_MODEL,
      max_tokens: 4096,
      system:     GRADING_SYSTEM,
      messages:   [{ role: 'user', content }],
    }),
    muteHttpExceptions: true,
  });

  const body = JSON.parse(res.getContentText());
  if (body.error) throw new Error(body.error.message);

  return parseJson(body.content[0].text);
}

// ═══════════════════════════════════════════════════════════════
// 오답노트 시트 저장
// 열 순서: 학생이름, 문제번호, 정답여부, 오답유형, 첨삭자, AI해설
// ═══════════════════════════════════════════════════════════════
function saveToSheet(studentName, unitName, result) {
  const ss    = SpreadsheetApp.getActiveSpreadsheet();
  const sheet = ss.getSheetByName(WRONG_ANSWER_SHEET);
  if (!sheet) return;

  const rows = [];
  for (const p of (result.problems || [])) {
    rows.push([
      studentName,
      p.problem_number || '',
      p.is_correct ? 'O' : 'X',
      p.is_correct ? '' : (p.error_type || ''),
      'AI',
      p.feedback || '',
    ]);
  }

  if (rows.length > 0) {
    sheet.getRange(sheet.getLastRow() + 1, 1, rows.length, 6).setValues(rows);
  }
}

// ═══════════════════════════════════════════════════════════════
// Discord 알림
// ═══════════════════════════════════════════════════════════════
function sendDiscord(text) {
  UrlFetchApp.fetch(DISCORD_WEBHOOK_URL, {
    method: 'post',
    contentType: 'application/json',
    payload: JSON.stringify({ content: text }),
    muteHttpExceptions: true,
  });
}

function sendGradingEmbed(studentName, unitName, result) {
  const total   = result.total_problems || 0;
  const correct = result.correct_count  || 0;
  const wrong   = total - correct;
  const pct     = total > 0 ? Math.round(correct / total * 100) : 0;
  const color   = pct >= 80 ? 5763719 : pct >= 60 ? 16776960 : 15548997;

  // 오답 유형 집계
  const typeCounts = {};
  for (const p of (result.problems || [])) {
    if (!p.is_correct && p.error_type) {
      typeCounts[p.error_type] = (typeCounts[p.error_type] || 0) + 1;
    }
  }
  const typeStr = Object.entries(typeCounts)
    .sort((a, b) => b[1] - a[1])
    .map(([k, v]) => `${k} ${v}건`)
    .join(' / ') || '없음';

  const embed = {
    title:  `✅ 채점 완료 — ${studentName}`,
    color,
    fields: [
      { name: '단원',     value: unitName || '미기재',                     inline: true },
      { name: '점수',     value: `${correct}/${total} (${pct}%)`,          inline: true },
      { name: '오답',     value: `${wrong}건`,                             inline: true },
      { name: '오답 유형', value: typeStr,                                  inline: false },
      { name: '종합 피드백', value: result.overall_feedback || '—',        inline: false },
    ],
  };

  UrlFetchApp.fetch(DISCORD_WEBHOOK_URL, {
    method: 'post',
    contentType: 'application/json',
    payload: JSON.stringify({ embeds: [embed] }),
    muteHttpExceptions: true,
  });
}

// ═══════════════════════════════════════════════════════════════
// JSON 파싱 (Claude 응답에서 JSON 블록 추출)
// ═══════════════════════════════════════════════════════════════
function parseJson(text) {
  const match = text.match(/```(?:json)?\s*(\{[\s\S]*?\})\s*```/);
  try {
    return JSON.parse(match ? match[1] : text.trim());
  } catch (_) {
    return { problems: [], overall_feedback: text.slice(0, 200), total_problems: 0, correct_count: 0 };
  }
}

// ═══════════════════════════════════════════════════════════════
// 프롬프트
// ═══════════════════════════════════════════════════════════════
const GRADING_SYSTEM = `당신은 수학 과외 선생님의 숙제 채점 도우미입니다.
반드시 JSON 형식으로만 응답하고, JSON 외 다른 텍스트는 포함하지 마세요.`;

const GRADING_PROMPT = `다음 숙제 이미지/PDF를 분석해서 아래 JSON 형식으로만 응답해주세요.

오답 유형:
- "개념부족": 개념 이해 부족
- "계산실수": 계산 과정 단순 실수
- "풀이순서": 풀이 방법/순서 오류
- "문제이해": 문제 해석 오류
- "기타"

\`\`\`json
{
  "total_problems": 문제수,
  "correct_count": 맞은문제수,
  "overall_feedback": "전반적인 한 줄 피드백",
  "problems": [
    {
      "problem_number": "1",
      "is_correct": true,
      "error_type": null,
      "feedback": "잘 풀었어요!"
    },
    {
      "problem_number": "2",
      "is_correct": false,
      "error_type": "계산실수",
      "feedback": "공식은 맞는데 마지막 계산에서 실수했어요."
    }
  ]
}
\`\`\``;
