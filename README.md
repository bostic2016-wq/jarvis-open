# Jarvis Open

Local playbook compliance checker for **Jarvis FFootball site** and **Jarvis Outreach & Email Gen tool**.

Scores those two repos against vault playbooks 01/02 (`agent-workflow`, `simplicity-and-teaching`). Never edits target repos.

## Setup

```bash
cd ~/.cursor/jarvis-open
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # optional: OPENROUTER_API_KEY for Layer 2
```

Open `~/.cursor/jarvis-open` as your Cursor workspace when developing this tool.

## Usage

```bash
# Layer 1 only (no API key)
python -m jarvis_open check --layer 1

# Both layers (needs eval gate + OPENROUTER_API_KEY)
python evals/run_evals.py
python -m jarvis_open check

# Write vault report
python -m jarvis_open check --write-vault
```

Exit codes: `0` no failures, `1` failures found, `2` config/runtime error.

## Model selection

Default: `google/gemini-2.0-flash-001` via `JARVIS_OPEN_MODEL`. README documents optional A/B with other OpenRouter models — not required for ship.

## First run

1. `python evals/run_evals.py` — writes `evals/last_run.json` (gitignored)
2. Layer 2 runs only when eval gate passes and API key is set
