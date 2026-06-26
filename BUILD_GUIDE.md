# PM AI Signal Tracker — Build Guide
# Step-by-step from your Mac to a running agent

---

## What you have

All files are pre-built and reviewed. Your job is to put them in the
right places and run the right commands. No code to write.

```
pm-ai-signal-tracker/
├── app/
│   └── agent.py                    ← Full workflow, all logic
├── tests/
│   ├── test_agent.py               ← Pytest suite (tools + hooks)
│   └── eval/
│       ├── judge-instruction.md    ← LLM-as-judge scoring rubric
│       └── datasets/
│           └── signals-dataset.json ← 12 eval cases
├── .agents/
│   ├── CONTEXT.md                  ← Agent brain (auto-loaded by Antigravity)
│   ├── hooks.json                  ← Execution gates
│   ├── scripts/
│   │   ├── validate_search.py      ← Blocks PII + injection before search
│   │   └── validate_memory_write.py ← Validates before memory writes
│   └── skills/
│       └── japan-context/
│           ├── SKILL.md            ← Progressive disclosure entry point
│           └── resources/
│               └── JAPAN_REFERENCE.txt ← Japan knowledge base
├── pyproject.toml                  ← Dependencies
├── .pre-commit-config.yaml         ← Semgrep security gates
├── .env.example                    ← Credential template (safe to commit)
└── BUILD_GUIDE.md                  ← This file
```

---

## Before you start

You need:
- [ ] Antigravity IDE installed on your Mac
- [ ] `uvx google-agents-cli setup` run at least once (installs agents-cli + 7 ADK skills)
- [ ] A Google AI Pro account (you have this)
- [ ] A SerpApi account for web search — free tier at serpapi.com gives 100 searches/month
  → Get your API key at: https://serpapi.com/manage-api-key
- [ ] Your Gemini API key from: https://aistudio.google.com/app/apikey

---

## PHASE 1 — Set up on your Mac (10 min, no Antigravity quota)

### Step 1 — Place the project folder

Unzip the downloaded file. You'll get a folder called `pm-ai-signal-tracker`.
Place it wherever you keep code on your Mac, e.g.:

```bash
~/code/pm-ai-signal-tracker/
```

### Step 2 — Create your .env file

Copy `.env.example` to `.env` and fill in your keys:

```bash
cd ~/code/pm-ai-signal-tracker
cp .env.example .env
```

Open `.env` and set:
```
GEMINI_API_KEY=your-key-from-aistudio
SEARCH_API_KEY=your-key-from-serpapi
GOOGLE_GENAI_USE_ENTERPRISE=FALSE
```

⚠️ Never commit `.env` to git. It is already in `.gitignore`.

### Step 3 — Install dependencies

```bash
cd ~/code/pm-ai-signal-tracker
uv sync --extra dev
```

This installs: `google-adk`, `pydantic`, `requests`, `pytest`, `semgrep`, `pre-commit`.

### Step 4 — Install pre-commit hooks

```bash
pre-commit install
```

This activates Semgrep scanning on every `git commit`.
Verify it worked:
```bash
pre-commit run --all-files
```

Expected: it runs, may show some warnings, should not block.

### Step 5 — Run pytest locally (no quota used)

```bash
uv run pytest tests/test_agent.py -v
```

This tests your tools and hooks without calling any LLM.
Expected: most tests pass. Hook tests require the scripts to be in place — they are.

If any tests fail, check the error message and come back to Claude before
moving to Antigravity.

---

## PHASE 2 — Antigravity Session 1: Scaffold + verify (15-20 min, low quota)

**Goal:** Get Antigravity to recognise the project structure and confirm
it can read all the files. No code generation needed — everything is pre-built.

### Step 6 — Open Antigravity

1. Open Antigravity IDE
2. Open the folder: `~/code/pm-ai-signal-tracker`
3. Set tool permission mode to **Request-Review** (default)
   → This makes Antigravity pause before running any command so you can verify

### Step 7 — Paste this prompt into Antigravity (exact wording)

```
Read the project structure and .agents/CONTEXT.md. 
Give me a brief summary of what this agent does and confirm 
you can see all the key files.
```

Expected response: Antigravity summarises the PM AI Signal Tracker, 
mentions the Japan PM lens, lists the files it can see.

This costs almost no quota — it's just a read operation.

### Step 8 — Paste this second prompt

```
Run: uv run pytest tests/test_agent.py -v
Report the results without fixing anything yet.
```

Expected: pytest runs, you see pass/fail per test.
If all green → proceed to Step 9.
If red → note which tests failed and come back to Claude to fix before Step 9.

### Step 9 — Paste this third prompt

```
Run: agents-cli lint
Report any issues found.
```

Expected: lint runs, may show style warnings, should not show errors.

**Session 1 is done when:** pytest runs (even with some failures is OK at this
stage) and agents-cli lint completes.

---

## PHASE 3 — Antigravity Session 2: Playground test (30-45 min, main quota spend)

**Goal:** Run the agent against your eval dataset in the playground.
Fix any runtime breaks. Validate the Japan lens is working.

⚠️ This is your biggest quota spend. Do Steps 10-12 carefully.

### Step 10 — Start the playground

Paste into Antigravity:
```
Run: agents-cli playground
```

This opens http://127.0.0.1:8080/dev-ui/?app=app in your browser.

### Step 11 — Test the scheduled digest path

In the playground UI, send:
```
scheduled
```

Expected:
- Agent runs search queries
- Classifier produces signals with gem scores
- HITL prompt appears if any gem 5 signals found
- Formatter produces a digest in English
- Memory write confirmation at the bottom

If something breaks, copy the error and come back to Claude.

### Step 12 — Test the on-demand path

In the playground UI, send:
```
What were the most important AI signals for Japan this week?
```

Expected:
- Agent reads from memory (populated in Step 11)
- Formatter produces a direct answer in English

### Step 13 — Run the eval dataset

Paste into Antigravity:
```
Run the eval dataset against the agent:
agents-cli eval run --dataset tests/eval/datasets/signals-dataset.json

Use tests/eval/judge-instruction.md as the judge instruction.
Report results per eval case with PASS / FAIL / CRITICAL FAIL.
```

Target: 10+ of 12 cases PASS. 
Any CRITICAL FAIL (security or English-only violation) must be fixed before deployment.

---

## PHASE 4 — Antigravity Session 3: Deploy (20 min, low quota)

**Goal:** Deploy to Agent Runtime so the scheduled digest can run autonomously.

### Step 14 — Deploy to Agent Runtime

Paste into Antigravity:
```
Deploy this agent to Agent Runtime.
Tell me each gcloud command you run before running it.
```

Review each command before approving (Request-Review mode).

### Step 15 — Verify deployment

```
agents-cli deploy status
agents-cli logs --follow
```

Send a test query to the deployed endpoint to confirm it responds.

### Step 16 — Set up the daily schedule

In Google Cloud Console → Cloud Scheduler:
- Create a job that hits your Agent Runtime endpoint daily at 08:00 JST
- Payload: `{"input": "scheduled"}`

---

## Submission checklist (before July 6)

- [ ] Agent runs scheduled digest end-to-end without errors
- [ ] Agent handles on-demand queries referencing past memory
- [ ] HITL triggers correctly for gem 5 signals
- [ ] All outputs in English (even from Japanese sources)
- [ ] Eval: 10+ of 12 cases pass, 0 CRITICAL FAILs
- [ ] Hooks block injection and PII in search queries
- [ ] Deployed to Agent Runtime
- [ ] Kaggle writeup explains the Japan PM lens differentiator
- [ ] Video demo: show scheduled digest + one on-demand query + one HITL trigger

---

## If something breaks — what to bring back to Claude

For any error in Antigravity, copy:
1. The exact error message
2. Which step you were on
3. Which prompt you sent

Claude has full context of this project and can fix it in one session
without you re-explaining anything.

---

## File reference

| File | Purpose | When you touch it |
|------|---------|-------------------|
| `app/agent.py` | Full agent workflow | Only if Claude edits it |
| `.agents/CONTEXT.md` | Agent brain | Read-only — Antigravity loads it |
| `.agents/hooks.json` | Execution gates | Read-only |
| `.agents/scripts/validate_search.py` | Search safety hook | Read-only |
| `.agents/scripts/validate_memory_write.py` | Memory safety hook | Read-only |
| `.agents/skills/japan-context/SKILL.md` | Skill entry point | Read-only |
| `.agents/skills/japan-context/resources/JAPAN_REFERENCE.txt` | Japan knowledge | Read-only |
| `tests/test_agent.py` | Pytest suite | Run it, don't edit |
| `tests/eval/datasets/signals-dataset.json` | Eval cases | Run it, don't edit |
| `tests/eval/judge-instruction.md` | Judge rubric | Reference only |
| `pyproject.toml` | Dependencies | Read-only |
| `.pre-commit-config.yaml` | Semgrep config | Read-only |
| `.env` | Your API keys | Fill in once, never commit |
| `.env.example` | Key template | Already done |
