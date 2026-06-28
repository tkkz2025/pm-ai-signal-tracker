# PM AI Signal Tracker — Project Writeup

## The Problem

I work as a PM on AI products in Japan. Every day I face the same problem: too much AI news, most of it noise for my context, and the small fraction that matters requires significant domain knowledge to interpret correctly.

Japan has a structural tension that makes this harder than it sounds. The government is pushing hard for AI adoption — Japan's Ministry of Economy, Trade and Industry (METI) AI Strategy, the AI Nippon initiative, SoftBank's OpenAI partnership. But enterprise adoption is slow due to slow consensus-driven approval culture, risk aversion, and lifetime employment norms. A PM in this market needs to track both: where government is pulling the market, and where enterprise inertia is the real constraint.

Existing tools answer "what happened?" I need "so what for my product decisions in Japan?"

---

## What I Built

A three-mode agent built on the Agent Development Kit (ADK) that delivers a scheduled daily AI news digest, alerts on breaking events, and handles on-demand queries. 

All user interactions happen via the Telegram bot called **AI PM Signal Tracker**, which communicates asynchronously with our FastAPI server using Google Cloud Pub/Sub message envelopes.

The three-mode design is tightly integrated: the scheduled digest filters and logs daily insights, the background monitor flags high-urgency breaking news, and the on-demand query mode lets users query this accumulated historical memory to answer retrospective questions like "how has OpenAI's Japan strategy shifted this month?" The tool gets smarter and more valuable over time.

Every news item is classified into one of six strategic categories, scored 1–5 on Japan strategic relevance (gem score), and output with an explicit Japan angle and strategic signal.

**Three Operating Modes:**
1. **`digest`** (daily at 9am JST) — Aggregates and translates the last 24h AI news into a single structured HTML message pushed via Pub/Sub to the Telegram bot.
2. **`monitor`** (every 3h background scan) — Evaluates recent news and triggers a proactive alert *only* if a highly critical, market-shifting breaking event (`breaking=True`) is discovered.
3. **`query`** (on-demand Q&A) — Answers natural language user queries directly in Telegram by retrieving historical context from memory and executing a clean, time-limit-free general web search.

**Six signal categories:**
- **Policy & sovereignty** — METI directives and government moves.
- **Model & capability release** — new model launches and benchmark jumps.
- **Infrastructure & compute** — cloud, chips, data centers.
- **Enterprise adoption** — who is deploying AI and with what outcome.
- **Competitive moves** — M&A, partnerships, strategic shifts.
- **Research & disruptor radar** — papers filtered by product implication, not technical merit.

---

## What Makes It Different

Four design decisions reflect real PM work in Japan that a generic agent would miss:

**Government ahead of enterprise.** Japan passed its first AI law in 2025, committed $65 billion to AI infrastructure through 2030, and framed the entire strategy as national recovery — the government has openly said Japan is behind. Policy moves here consistently precede enterprise adoption by 12–24 months, making them some of the most actionable signals a Japan PM can track.

**The Japan commitment lens.** OpenAI, Anthropic, and Cohere have Japan offices. Their model releases are gems — localization and enterprise sales follow. The classifier cross-references a handcrafted list of ~20 Japan-committed companies, so an English-first release gets scored on commitment, not language.

**Use cases abroad as leading indicators.** A German manufacturer deploying AI for predictive maintenance is noise for most PMs. For a Japan PM it's a gem — Japan's manufacturing sector is the likely next market, and the adoption lag makes it actionable today.

**Local Japanese AI labs as first-class signals.** NTT, Fujitsu, Sakana AI, and Preferred Networks are building models and infrastructure specifically for the Japanese market. The agent tracks these alongside global labs — a locally fine-tuned model that handles Japanese enterprise documents is often more actionable for a Japan PM than a frontier release from abroad.

---

## Architectural Choices

**Separation of Concerns (Classifier vs. Formatters).** We split the classification engine from the output formatters. The classifier runs at temperature 0 for strict, deterministic analysis and scoring, while the formatters run at temperature 0.2 to generate natural summaries without hallucinating facts.

**Bilingual Title-Similarity Deduplication.** The search phase runs 8 queries concurrently and filters them through a Python title-similarity check. If an article overlaps with a previously seen story, it is discarded. This keeps the feed clean, eliminates duplicate signal generation, and reduces context window costs.

**Self-Healing URL Resolver.** To prevent the agent from delivering broken or hallucinated links, a Python validation layer scores headlines against search results (weighing proper nouns and numbers heavily). If the LLM assigns a wrong ID, Python overrides it and self-heals the link to the correct URL before delivery.

**Clean Q&A Web Search.** Q&A mode strips conversational query filler in Python, bypasses Google News limits, and executes a general web search without time limits, guaranteeing highly relevant result pages for startup queries or general concepts.

---

## Course Concepts Applied

* **State & Workflow Orchestration:** Built a conditional routing DAG using the ADK 2.0 framework, leveraging context state transitions to orchestrate specialized classification and formatting agents.
* **Persistent Long-Term Memory:** Utilized file-based memory stores to persist structured daily digests, enabling cross-session query retrieval and retrospective analysis.
* **Progressive Disclosure:** Applied ADK Agent Skills to dynamically load Japanese market context only when processing signals, optimizing prompt efficiency.
* **Asynchronous Pub/Sub Integration:** Connected the user-facing Telegram bot asynchronously with the FastAPI application server using Pub/Sub message envelopes.
* **Security & Execution Gates:** Deployed pre-execution script hooks (`hooks.json`) to validate queries and block prompt injections and private identifiers before they reach public search engine APIs.
* **Deterministic Code Validation:** Interleaved LLM nodes with programmatic Python nodes to verify, deduplicate, and self-heal outputs (like source URL mappings) directly in code.
* **Rigorous Evaluation Metrics:** Created a local unit test suite and a 12-case LLM-as-a-judge dataset to grade the agent on domain classification and safety.
