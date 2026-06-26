# PM AI Signal Tracker

> A dual-mode ADK 2.0 agent that delivers a daily AI news digest filtered through a Japan PM lens — translating global AI signals into product strategy implications for product managers working on AI products in Japan.

Built for the [Kaggle × Google 5-Day AI Agents Vibe Coding Course](https://www.kaggle.com/competitions/vibecoding-agents-capstone-project) capstone (July 2026).

---

## What it does

Most AI news digests answer **"what happened?"**. This agent answers **"so what for my product decisions in Japan?"**

Every news item is classified into one of six signal categories, scored 1–5 on Japan strategic relevance (gem score), and translated into a PM-lens output with Japan angle and strategic signal. Gem score 5 signals trigger a human-in-the-loop review before being surfaced.

**Two entry points:**
- `scheduled` — autonomous daily digest of last 24h AI news, filtered through the Japan PM lens
- Any natural language query — on-demand signal lookup with memory retrieval

---

## Signal taxonomy

| Category | Japan filter |
|----------|-------------|
| Policy & sovereignty | METI directives, AI Nippon initiative, data localisation |
| Model & capability release | Japan-committed companies (OpenAI Japan, Anthropic Japan, Cohere, etc.) — English-first is NOT noise |
| Infrastructure & compute | AWS/Azure/Google DC builds in Japan, Rapidus semiconductor, TSMC Kumamoto |
| Enterprise adoption | Japan domestic deployments + global use case scouting (12–18 month lag indicator) |
| Competitive moves | SoftBank/OpenAI, NTT-Docomo AI, Sony AI, KK/GK entity formation |
| Research & disruptor radar | Filtered by product implication: does this create or destroy a product assumption? |

---

## Architecture

```
START → detect_trigger
      → [scheduled: prepare_digest_queries | on_demand: on_demand_router]
      → classifier (LlmAgent, gemini-2.5-flash, output_schema=DigestSignals)
      → route_by_gem_score
      → [gem_score=5: build_hitl_prompt → HITL → formatter]
      → [gem_score<5: formatter]
      → store_and_finish → END
```

**Key design decisions:**
- `DigestSignals` Pydantic schema enforces structured output from classifier
- HITL uses `create_request_input_event` — signals written to disk before interrupt, recovered via `load_hitl_pending()` after ADK state reset on resume
- Memory stored as dated JSON files in `.agents/memory/` for on-demand retrieval
- Bilingual search queries (English + Japanese) to catch Japan-only sources
- `tbs=qdr:d` SerpApi filter enforces 24h recency on all searches

**Course concepts applied:**
- ADK 2.0 workflow with conditional routing (Days 1–2)
- Session state + file-based long-term memory (Day 3)
- Progressive disclosure via Antigravity Skills (Day 3)
- Pydantic input validation, hooks.json execution gates, Semgrep pre-commit (Day 4)
- LLM-as-judge eval dataset with 12 cases (Day 4)
- Human-in-the-loop for high-stakes signals (Day 4)

---

## Setup

### Prerequisites
- Python 3.11+
- [uv](https://astral.sh/uv) package manager
- Gemini API key from [Google AI Studio](https://aistudio.google.com/app/apikey)
- SerpApi key from [serpapi.com](https://serpapi.com/manage-api-key) (free tier: 100 searches/month)

### Install

```bash
git clone https://github.com/YOUR_USERNAME/pm-ai-signal-tracker
cd pm-ai-signal-tracker

uv sync --extra dev
```

### Configure

```bash
cp .env.example .env
# Edit .env and fill in your API keys
```

### Run

```bash
uv run adk web
# Opens http://127.0.0.1:8000
```

Send `scheduled` for a daily digest, or any natural language query for on-demand signals.

### Test

```bash
uv run pytest tests/test_agent.py -v
# 29 tests — schemas, tools, hooks
```

---

## Project structure

```
pm-ai-signal-tracker/
├── app/
│   └── agent.py                    # Full workflow, all logic
├── tests/
│   ├── test_agent.py               # Pytest suite (29 tests)
│   └── eval/
│       ├── judge-instruction.md    # LLM-as-judge rubric
│       └── datasets/
│           └── signals-dataset.json # 12 eval cases
├── .agents/
│   ├── CONTEXT.md                  # Agent brain (Antigravity auto-loads)
│   ├── hooks.json                  # Pre-tool execution gates
│   ├── scripts/
│   │   ├── validate_search.py      # Blocks PII + injection before search
│   │   └── validate_memory_write.py
│   └── skills/
│       └── japan-context/          # Progressive disclosure Japan knowledge base
├── pyproject.toml
├── .pre-commit-config.yaml         # Semgrep security gates
└── .env.example
```

---

## Eval dataset

12 cases covering:
- Happy path gems (policy, model release, infrastructure, global use case scouting)
- Edge cases (English-first model from Japan-committed company = NOT noise)
- Noise identification
- On-demand query handling
- Security: prompt injection in news content
- Security: PII in search query (hook validation)
- Japanese-source, English-output rule

---

## Track

**Agents for Business** — PM decision-support tool for AI product managers operating in the Japan market.

---

## Author

Built by a PM working on AI products in Japan, as a capstone for the Kaggle × Google 5-Day AI Agents Vibe Coding Course (June 2026).
