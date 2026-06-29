# AI PM Signal Tracker

> A three-mode ADK 2.0 agent that delivers a daily AI news digest, alerts on breaking events, and answers on-demand questions—all filtered through a Japan PM lens to translate global AI news into strategic product decisions.

Built for the [Kaggle × Google 5-Day AI Agents Vibe Coding Course](https://www.kaggle.com/competitions/vibecoding-agents-capstone-project) capstone (July 2026).

---

## What it does

Most AI news digests answer **"what happened?"**. This agent answers **"so what for my product decisions in Japan?"**

Every news item is classified into one of six signal categories, scored 1–5 on Japan strategic relevance (gem score), and translated into a PM-focused output detailing the Japan angle and strategic signal.

**Three Operating Modes:**
1. **`digest`** (daily at 9am JST) — Autonomous daily digest of the last 24h AI news, formatted into a structured, single-message HTML payload for Telegram and the console.
2. **`monitor`** (every 3h) — Background scan that triggers a proactive alert on Telegram *only* when a highly critical, market-shifting breaking event (`breaking=True`) is discovered.
3. **`query`** (on-demand) — Direct Q&A system that processes natural language queries sent to the Telegram bot, performs memory retrieval and a clean, general web search, and returns a concise, direct answer.

---

## Signal Taxonomy

| Category | Japan filter |
|----------|-------------|
| **Policy & sovereignty** | METI directives, AI Nippon initiative, data localization rules |
| **Model & capability release** | Japan-committed companies (OpenAI Japan, Anthropic Japan, Sakana AI, etc.) — English-first is NOT noise |
| **Infrastructure & compute** | AWS/Azure/Google DC builds in Japan, Rapidus, TSMC Kumamoto |
| **Enterprise adoption** | Japanese enterprise deployments + global use case scouting (lag indicators) |
| **Competitive moves** | SoftBank/OpenAI, NTT-Docomo AI, Sony AI partnerships |
| **Research & disruptor radar** | Implication lens: does this create or destroy a product assumption? |

---

## Architecture

```
                      START 
                        │
                        ▼
                  detect_trigger
                  /            \
           (scan) /              \ (query)
                 ▼                ▼
     prepare_digest_queries   on_demand_router
                 │                │
                 │                ▼
                 │            after_on_demand_router
                 \                /
                  ▼              ▼
                     classifier
                         │
                         ▼
                 route_by_gem_score
                 /       │        \
        (digest)/        │(monitor)\ (query)
               ▼         │          ▼
       digest_formatter  │   query_formatter
               │         ▼          │
               │   monitor_finish   │
               \         │          /
                ▼        ▼         ▼
             store_and_finish (or END)
```

**Key Architectural Features:**
* **Bilingual Title Deduplication:** Aggregates 8 concurrent searches and runs a title-similarity filter in Python to discard overlapping duplicate stories (e.g. HokaNews vs TechCrunch covering the same ban lift), ensuring a clean classifier feed.
* **Self-Healing URL Resolution:** Evaluates proper nouns, numbers (weight=5), and cross-lingual synonyms (weight=3) to map LLM headlines to source URLs with 100% precision. Python overrides incorrect LLM IDs if another article is a substantially better match.
* **On-Demand Q&A Search:** Cleans conversational query phrasing (like `"how about"`) in Python, bypasses the 24-hour time limit, and runs a general Google Web search instead of news-only search to gather rich context pages.
* **ADK 2.0 Contract Compliance:** Fully utilizes the `Event(output=...)` signature to prevent parameters from being ignored during state transitions.

---

## Setup

### Prerequisites
- Python 3.11+
- [uv](https://astral.sh/uv) package manager
- Gemini API key from [Google AI Studio](https://aistudio.google.com/app/apikey)
- SerpApi key from [serpapi.com](https://serpapi.com/manage-api-key)
- Telegram Bot Token + Chat ID (optional, logs fallback to console if not set)

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

### Run Server

```bash
uv run adk web
# Opens the ADK app at http://127.0.0.1:8000
```

### Run Telegram Bot Poller (Local daemon)

```bash
uv run python app/telegram_poll.py
# Polls Telegram bot for user questions and forwards them as Pub/Sub triggers to the server
```

---

## Test & Verify

### Running Unit & Integration Tests

We have a robust suite of **24 unit and integration tests** testing schemas, long-term memory operations, and hook security validations locally without invoking expensive API calls:

```bash
uv run pytest -v
# 24 tests passed successfully
```

### Running Evaluation Cases

The LLM-as-a-judge evaluation suite covers **12 scenarios** mapping exactly to our operating mode requirements (including empty results, monitor alerts, Q&A memory recall, and prompt injections):

```bash
agents-cli eval run --dataset tests/eval/datasets/signals-dataset.json
```

---

## Project Structure

```
pm-ai-signal-tracker/
├── app/
│   ├── agent.py                    # Main agent workflow, nodes, and LlmAgents
│   └── telegram_poll.py            # Telegram polling daemon (sends Pub/Sub queries)
├── tests/
│   ├── test_agent.py               # Local Pytest suite (24 tests)
│   └── eval/
│       ├── judge-instruction.md    # LLM-as-judge scoring rubric & hard failures
│       └── datasets/
│           └── signals-dataset.json # 12 structured eval scenarios
├── .agents/
│   ├── CONTEXT.md                  # Project context
│   ├── hooks.json                  # Pre-tool execution security gates
│   ├── scripts/
│   │   ├── validate_search.py      # Hooks blocking PII & injections
│   │   └── validate_memory_write.py
│   └── skills/
│       └── japan-context/          # Japan reference database
├── ARCHITECTURE.md                 # Technical spec and implementation design
├── pyproject.toml
├── .pre-commit-config.yaml         # Semgrep security pre-commit check
└── .env.example
```

---

## Track

**Agents for Business** — PM decision-support tool for AI product managers operating in the Japan market.

---

## Author

Built by a PM working on AI products in Japan, as a capstone for the Kaggle × Google 5-Day AI Agents Vibe Coding Course (July 2026).
