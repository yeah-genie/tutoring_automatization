Read AGENTS.md. It explains how to check a maths worksheet with this repo (Task A) and how to build
and verify a new quiz (Task B). Run the tests with `python tests/test_mathcheck.py && python tests/test_lite.py`.
After editing `mathcheck/curricula/*.yaml` or `integrations/engine/mathcheck_lite.py`, run
`python tools/build_integrations.py`. That script regenerates the JSON files, the skill copy and the hash in AGENTS.md.
Never commit student names or other personal data. This repository is public.
