# PM AI Signal Tracker — Project Writeup

## The Problem

I work as a PM on AI products in Japan. Every day I face the same problem: too much AI news, most of it noise for my context, and the small fraction that matters requires significant domain knowledge to interpret correctly.

Japan has a structural tension that makes this harder than it sounds. The government is pushing hard for AI adoption — METI's AI Strategy, the AI Nippon initiative, SoftBank's OpenAI partnership. But enterprise adoption is slow due to ringi consensus culture, risk aversion, and lifetime employment norms. A PM in this market needs to track both: where government is pulling the market, and where enterprise inertia is the real constraint.

Existing tools answer "what happened?" I need "so what for my product decisions in Japan?"

---

## What I Built

A three-mode ADK 2.0 agent that delivers a scheduled daily AI news digest, alerts on breaking events, and answers on-demand questions—all filtered through a Japan PM lens.

The core idea is signal translation, not aggregation. Every news item is classified into one of six strategic categories, scored 1–5 on Japan strategic relevance (gem score), and output with an explicit Japan angle and strategic signal.

**Three Operating Modes:**
1. **`digest`** (daily at 9am JST) — Aggregates and translates the last 24h AI news into a single structured HTML message for Telegram and the console.
2. **`monitor`** (every 3h background scan) — Evaluates recent news and triggers a proactive alert *only* if a highly critical, market-shifting breaking event (`breaking=True`) is discovered.
3. **`query`** (on-demand Q&A) — Answers natural language user queries directly by retrieving historical context from memory and executing a clean, time-limit-free general web search.

**Six signal categories, each with a Japan-specific lens:**
- **Policy & sovereignty** — METI directives are leading indicators of where product demand forms, giving PMs 12–24 months of advance signal.
- **Model & capability release** — Global model launches matter when the company is already committed to Japan.
- **Infrastructure & compute** — Data center builds in Japan directly remove the enterprise adoption blockers.
- **Enterprise adoption** — Two lenses: Japan domestic deployments + global use case scouting (proven deployments abroad are 12–18 month leading indicators for Japan).
- **Competitive moves** — Japan's tech giants move via alliances; watch for foreign AI companies establishing local legal entities in Japan.
- **Research & disruptor radar** — Filtered by one question: does this create or destroy a product assumption?

---

## What Makes It Different

Four design decisions reflect real PM work in Japan that a generic agent would miss:

**The Japan commitment lens.** OpenAI, Anthropic, and Cohere have Japan offices. Their model releases are gems — localization and enterprise sales follow. The classifier cross-references a curated list of Japan-committed companies.

**Use cases abroad as leading indicators.** A German manufacturer deploying AI for predictive maintenance is noise for most PMs. For a Japan PM it's a gem — Japan's manufacturing sector is the likely next market, and the adoption lag makes it actionable today.

**Government ahead of enterprise.** Japan's policy signals consistently precede enterprise adoption. The agent is tuned to treat government moves as product strategy input, not background news.

**Local Japanese AI labs as first-class signals.** NTT, Fujitsu, Sakana AI, and Preferred Networks are building models and infrastructure specifically for the Japanese market. The agent tracks these alongside global labs — a locally fine-tuned model that handles Japanese enterprise documents is often more actionable for a Japan PM than a frontier release from abroad.

**Self-Healing URL Alignment.** Generic agents frequently hallucinate URLs or attach wrong links under concurrency. This agent utilizes a custom Python-assisted matching system:
- **Bilingual Title-Similarity Deduplicator:** Evaluates Kanji/Katakana and English keyword overlaps to filter out duplicate coverage of the same news event across different feeds.
- **Weighted Term Matcher:** Scores headlines against search results (proper nouns and numbers get weight 5, Japan synonyms get weight 3, generic words are ignored). Python overrides the LLM's suggested index if another article is a substantially stronger match.

---

## Course Concepts Applied

* **ADK 2.0 Workflow:** Built a complete DAG with conditional three-way routing and three specialized `LlmAgents` (`digest_formatter`, `query_formatter`, `on_demand_router`).
* **Long-Term Memory:** Implemented file-based state persistence to store and recall historical digests for on-demand query retrieval.
* **Progressive Disclosure:** Incorporated Antigravity Skills (`japan-context`) to dynamically feed Japan-specific market rules to the agent only when required.
* **Security & Execution Gates:** Deployed `hooks.json` script hooks (`validate_search.py` and `validate_memory_write.py`) that run as secure pre-execution barriers to block prompt injections and PII.
* **Rigorous Testing & Evals:** Created a **24-case pytest suite** validating schemas and memory tools, paired with a **12-case LLM-as-a-judge dataset** checking mode routing, edge cases, and safety.
