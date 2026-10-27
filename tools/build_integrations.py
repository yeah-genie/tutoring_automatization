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
(eng / "curricula.json").write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
skill = ROOT / "integrations" / "claude-skill" / "worksheet-check" / "scripts"
skill.mkdir(parents=True, exist_ok=True)
for name in ("mathcheck_lite.py", "curricula.json"):
    shutil.copy(eng / name, skill / name)
print("curricula:", ", ".join(data))
