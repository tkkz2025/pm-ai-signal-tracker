# Antigravity Session 1 — Scaffold + Paste
# PM AI Signal Tracker
#
# INSTRUCTIONS FOR USE:
# 1. Open Antigravity IDE
# 2. Set tool permission mode to: Request-Review (default)
# 3. Open a new project folder called: pm-ai-signal-tracker
# 4. Paste PROMPT 1 first. Wait for it to complete before pasting PROMPT 2.
# 5. Do NOT paste both prompts at once — each must finish before the next.

# ============================================================
# PROMPT 1 — Scaffold the project structure
# ============================================================

Act as a senior Python engineer using Google ADK 2.0.

Scaffold a new ADK 2.0 agent project called pm-ai-signal-tracker using:
  agents-cli scaffold create pm-ai-signal-tracker --adk

Then create the following empty directory structure (do not write any code yet):

pm-ai-signal-tracker/
├── app/
│   └── __init__.py
├── tests/
│   ├── __init__.py
│   └── eval/
│       └── datasets/
├── .agents/
│   ├── scripts/
│   └── skills/
│       └── japan-context/
│           └── resources/
├── .env.example
└── .gitignore (exclude .env, __pycache__, .pytest_cache, *.pyc)

After creating the structure, run:
  agents-cli lint

Report what you created and any lint warnings.

# ============================================================
# PROMPT 2 — Paste in all pre-built files
# ============================================================

I have pre-built all the project files. Paste each one exactly as provided
into the correct path. Do not modify any content.

Files to create:

1. app/agent.py → [paste full agent.py content here]

2. .agents/CONTEXT.md → [paste full CONTEXT.md content here]

3. .agents/hooks.json → [paste full hooks.json content here]

4. .agents/scripts/validate_search.py → [paste full validate_search.py here]

5. .agents/scripts/validate_memory_write.py → [paste full validate_memory_write.py here]

6. .agents/skills/japan-context/SKILL.md → [paste full SKILL.md here]

7. .agents/skills/japan-context/resources/JAPAN_REFERENCE.txt → [paste full JAPAN_REFERENCE.txt here]

8. tests/eval/datasets/signals-dataset.json → [paste full signals-dataset.json here]

9. tests/eval/judge-instruction.md → [paste full judge-instruction.md here]

10. tests/test_agent.py → [paste full test_agent.py here]

11. pyproject.toml → [paste full pyproject.toml here]

12. .pre-commit-config.yaml → [paste full .pre-commit-config.yaml here]

13. .env.example → [paste full .env.example here]

After pasting all files, run:
  uv run pytest tests/test_agent.py -v

Report the test results. Do not fix any failures yet — just report them.

# ============================================================
# PROMPT 3 — Install pre-commit hooks (run after tests pass)
# ============================================================

Install the pre-commit hooks and verify they work:

  pre-commit install
  agents-cli lint

Report any issues found. Do not fix yet — just report.

# ============================================================
# SESSION 1 DONE CRITERIA
# ============================================================
# ✅ Project structure created
# ✅ All 13 files pasted in
# ✅ pytest runs (even if some tests fail — that's expected)
# ✅ pre-commit installed
#
# DO NOT start Session 2 until all of the above are confirmed.
# Session 2 = playground testing against eval dataset.
# Session 3 = deployment to Agent Runtime + Cloud Run.
