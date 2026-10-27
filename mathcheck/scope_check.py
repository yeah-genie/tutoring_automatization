"""단원 범위 검사.

curricula/<curriculum>.yaml 에 단원별 '이 단원에서 처음 나오는 개념'의 키워드를 적어 둔다.
퀴즈에서 고른 단원(chapters)에 속하지 않는 단원의 키워드가 문제·해설에 나오면 오류로 잡는다.
키워드 검사는 완벽하지 않으므로, 잡히지 않았다고 범위 안이라는 보장은 아님.
"""
from __future__ import annotations

import re
from pathlib import Path

import yaml

from .spec import Report

CURRICULA_DIR = Path(__file__).resolve().parent.parent / "curricula"


def load_curriculum(name: str) -> dict:
    path = CURRICULA_DIR / f"{name}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"단원 정보 파일이 없음: {path.name}")
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def check_scope(spec: dict) -> Report:
    rep = Report()
    try:
        cur = load_curriculum(spec["curriculum"])
    except FileNotFoundError as e:
        rep.add("warning", "범위", f"{e} → 범위 검사를 건너뜀")
        return rep
    chapters = cur["chapters"]
    allowed = set(spec.get("chapters", []))
    unknown = allowed - set(chapters)
    for u in unknown:
        rep.add("error", "범위", f"단원 '{u}'이(가) {spec['curriculum']} 단원 목록에 없음")
    # 허용 단원에 이미 나온 키워드는 다른 단원에 같이 있어도 괜찮다
    allowed_kw = {kw.lower() for ch in allowed & set(chapters) for kw in chapters[ch].get("keywords", [])}
    for q in spec.get("questions", []):
        qid = f"Q{q.get('id', '?')}"
        blob = " ".join(str(q.get(k, "")) for k in ("text", "solution", "final_answer", "diagram")).lower()
        for ch, info in chapters.items():
            if ch in allowed:
                continue
            for kw in info.get("keywords", []):
                k = kw.lower()
                if k in allowed_kw:
                    continue
                left = r"\b" if k[:1].isalnum() else ""
                right = r"\b" if k[-1:].isalnum() else ""
                pattern = left + re.escape(k) + right
                if re.search(pattern, blob):
                    rep.add("error", qid, f"범위 밖 개념 '{kw}' ({info.get('title', ch)} 단원)이 쓰임")
    return rep
