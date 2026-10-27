"""Regenerate integrations/engine/curricula.json from mathcheck/curricula/*.yaml and copy the
engine into the Claude skill folder. Run after editing a curriculum file."""
import json
import shutil
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
eng = ROOT / "integrations" / "engine"
data = {}
for f in sorted((ROOT / "mathcheck" / "curricula").glob("*.yaml")):
    cur = yaml.safe_load(f.read_text(encoding="utf-8"))
    data[f.stem] = cur
(eng / "curricula").mkdir(exist_ok=True)
for code, cur in data.items():
    (eng / "curricula" / f"{code}.json").write_text(json.dumps(cur, ensure_ascii=False, indent=1), encoding="utf-8")
(eng / "curricula.json").write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
skill = ROOT / "integrations" / "claude-skill" / "worksheet-check" / "scripts"
skill.mkdir(parents=True, exist_ok=True)
for name in ("mathcheck_lite.py", "curricula.json"):
    shutil.copy(eng / name, skill / name)
print("curricula:", ", ".join(data))

# keep the hash in AGENTS.md in sync (AIs use it to verify a hand-copied engine)
import hashlib
import re

digest = hashlib.sha256((eng / "mathcheck_lite.py").read_bytes()).hexdigest()
agents = ROOT / "AGENTS.md"
text = agents.read_text(encoding="utf-8")
agents.write_text(re.sub(r"(SHA-256 of mathcheck_lite.py: `)[0-9a-f]{64}(`)", rf"\g<1>{digest}\g<2>", text), encoding="utf-8")
print("sha256:", digest)
