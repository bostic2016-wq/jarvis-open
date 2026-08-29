# Layer 1 — deterministic checks

## safety
- **fail**: credential patterns in tracked source (sk-, Bearer, PEM, API_KEY assignments)
- **fail**: tracked `.env` in git
- **warn**: credential-like patterns only in `.env.example`, `evals/fixtures/`, or git-ignored paths (not test files)
- **fail**: test files with credential patterns always fail (test-fail beats gitignore)

## simplicity-02
- **fail**: narration comments (`# import`, `# return`, `// define`, etc.)
- **pass**: comments explaining business logic or edge cases

## simplicity-01
- **warn**: single source file > 400 lines (not a hard fail)

## Layer 2 — LLM judge (playbooks 01/02)

## agent-workflow
- **fail**: obvious over-engineering, unnecessary abstraction layers
- **fail**: change looks like full-file rewrite when a small edit would suffice (use diff context)
- **pass**: targeted, procedural changes

## simplicity-and-teaching
- **fail**: syntax-narration comments missed by Layer 1 heuristics
- **pass**: simple, direct code

## Omitted (not judgeable from code)
- Whether a plan was written first
- Whether agent stopped after 3 failed fixes
