# PM AI Signal Tracker — Project Writeup

## The Problem

I work as a PM on AI products in Japan. Every day I face the same problem: too much AI news, most of it noise for my context, and the small fraction that matters requires significant domain knowledge to interpret correctly.

Japan has a structural tension that makes this harder than it sounds. The government is pushing hard for AI adoption — Japan's Ministry of Economy, Trade and Industry (METI) AI Strategy, the AI Nippon initiative, SoftBank's OpenAI partnership. But enterprise adoption is slow due to slow consensus-driven approval culture, risk aversion, and lifetime employment norms. A PM in this market needs to track both: where government is pulling the market, and where enterprise inertia is the real constraint.

Existing tools answer "what happened?" I need "so what for my product decisions in Japan?"

---

## What I Built

A three-mode ADK 2.0 agent that delivers a scheduled daily AI news digest, alerts on breaking events, and handles on-demand queries—all filtered through a Japan PM lens.

The three-mode design is intentional: the scheduled digest accumulates structured signal history in memory, so on-demand queries can answer retrospective questions like "how has OpenAI's Japan strategy shifted this month?" The agent gets more useful over time, not just on the day you run it.

Every news item is classified into one of six strategic categories, scored 1–5 on Japan strategic relevance (gem score), and output with an explicit Japan angle and strategic signal.

**Three Operating Modes:**
1. **`digest`** (daily at 9am JST) — Aggregates and translates the last 24h AI news into a single structured HTML message for Telegram and the console.
2. **`monitor`** (every 3h background scan) — Evaluates recent news and triggers a proactive alert *only* if a highly critical, market-shifting breaking event (`breaking=True`) is discovered.
3. **`query`** (on-demand Q&A) — Answers natural language user queries directly by retrieving historical context from memory and executing a clean, time-limit-free general web search.

**Six signal categories:**
- Policy & sovereignty — METI directives and government moves
- Model & capability release — new model launches and benchmark jumps
- Infrastructure & compute — cloud, chips, data centers
- Enterprise adoption — who is deploying AI and with what outcome
- Competitive moves — M&A, partnerships, strategic shifts
- Research & disruptor radar — papers filtered by product implication, not technical merit

---

## What Makes It Different

Four design decisions reflect real PM work in Japan that a generic agent would miss:

**Government ahead of enterprise.** Japan passed its first AI law in 2025, committed $65 billion to AI infrastructure through 2030, and framed the entire strategy as national recovery — the government has openly said Japan is behind. Policy moves here consistently precede enterprise adoption by 12–24 months, making them some of the most actionable signals a Japan PM can track.

**The Japan commitment lens.** OpenAI, Anthropic, and Cohere have Japan offices. Their model releases are gems — localization and enterprise sales follow. The classifier cross-references a handcrafted list of ~20 Japan-committed companies, so an English-first release gets scored on commitment, not language.

**Use cases abroad as leading indicators.** A German manufacturer deploying AI for predictive maintenance is noise for most PMs. For a Japan PM it's a gem — Japan's manufacturing sector is the likely next market, and the adoption lag makes it actionable today.

**Local Japanese AI labs as first-class signals.** NTT, Fujitsu, Sakana AI, and Preferred Networks are building models and infrastructure specifically for the Japanese market. The agent tracks these alongside global labs — a locally fine-tuned model that handles Japanese enterprise documents is often more actionable for a Japan PM than a frontier release from abroad.

---

## Architectural Choices

**Four LLM nodes with different models and temperatures.** The classifier uses `gemini-2.5-flash` at temperature 0 — structured classification needs precision, not creativity. The digest and query formatters use the same model at temperature 0.2 — they need some variation to produce readable prose without drifting into hallucination.

**Pydantic output schema on the classifier.** Without `output_schema=DigestSignals`, the classifier drifts between structured JSON and prose. Enforcing the schema at the ADK layer means every classifier run produces validated, typed signals regardless of model behavior.

**File-based memory over session state.** ADK session state resets between workflow runs. Storing digests as dated JSON files in `.agents/memory/` means on-demand queries can retrieve signals from days ago — which is the core value of the three-mode design.

**Bilingual Title-Similarity Deduplication.** Aggregates 8 concurrent searches and runs a title-similarity filter in Python (`_deduplicate_articles`) to discard overlapping duplicate stories (e.g. HokaNews vs TechCrunch covering the same ban lift), ensuring a clean classifier feed and preventing duplicate signals.

**Self-Healing Weighted URL Matcher.** Prevents URL hallucinations by mapping LLM headlines to search results in Python using weighted scores (proper nouns/numbers get weight 5, Japanese synonyms get weight 3). Python overrules the LLM's suggested index if another article has a substantially stronger matching score.

---

## Course Concepts Applied

* **ADK 2.0 Workflow:** Built a complete DAG with conditional three-way routing and three specialized `LlmAgents` (`digest_formatter`, `query_formatter`, `on_demand_router`) plus the classifier.
* **Long-Term Memory:** Implemented file-based state persistence to store and recall historical digests for on-demand query retrieval.
* **Progressive Disclosure:** Incorporated Antigravity Skills (`japan-context`) to dynamically feed Japan-specific market rules to the agent only when required, preventing context rot in long classifier runs.
* **Security & Execution Gates:** Deployed `hooks.json` script hooks (`validate_search.py` and `validate_memory_write.py`) that run as secure pre-execution barriers to block prompt injections and PII before search fires, with Semgrep pre-commit scanning.
* **Rigorous Testing & Evals:** Created a **24-case pytest suite** validating schemas and memory tools, paired with a **12-case LLM-as-a-judge dataset** checking mode routing, edge cases, and safety.
* **Self-Healing Python Nodes:** Replaced brittle HITL (Human-in-the-loop) prompts with programmatically assisted LLM decision-making that validates and heals links automatically.
