# PM AI Signal Tracker — Project Writeup

## The Problem

I work as a PM on AI products in Japan. Every day I face the same problem: too much AI news, most of it noise for my context, and the small fraction that matters requires significant domain knowledge to interpret correctly.

Japan has a structural tension that makes this harder than it sounds. The government is pushing hard for AI adoption — Japan's Ministry of Economy, Trade and Industry (METI) AI Strategy, the AI Nippon initiative, SoftBank's OpenAI partnership. But enterprise adoption is slow due to slow consensus-driven approval culture, risk aversion, and lifetime employment norms. 

Because global frontier LLMs evolve week-by-week, a 12-18 month enterprise approval delay means Japanese companies risk building on obsolete model assumptions. A PM must track these signals in real-time to avoid lock-in to technical debt before project approval is even signed off.

Existing tools answer "what happened?" I need "so what for my product decisions in Japan?"

---

## What I Built

A three-mode agent built on the Agent Development Kit (ADK) that delivers a scheduled daily AI news digest, alerts on breaking events, and handles on-demand queries. 

All user interactions happen via the Telegram bot called **AI PM Signal Tracker**, which communicates with our FastAPI backend. The three-mode design is tightly integrated: the scheduled digest logs daily insights, the background monitor flags high-urgency breaking news, and the on-demand Q&A mode lets users query this accumulated historical memory alongside live web searches. The tool gets more valuable over time.

Every news item is classified into one of six strategic categories, scored 1–5 on Japan strategic relevance (gem score), and output with an explicit Japan angle and strategic signal.

**Three Operating Modes:**
1. **`digest`** (daily at 9am JST) — Aggregates and translates the last 24h AI news into a structured HTML message sent to the Telegram bot. To prevent notification fatigue, the digest uses a prioritized layout (Red Tier "Must-Read Gem 5" for high-impact items, Orange Tier "Watch Closely Gem 4", and Yellow Tier "On the Radar Gem 3" for headlines) allowing PMs to scan the landscape in under 30 seconds.
2. **`monitor`** (every 3h background scan) — Evaluates recent news and triggers a proactive alert *only* if a highly critical, market-shifting breaking event (`breaking=True`) is discovered.
3. **`query`** (on-demand Q&A) — Answers natural language user queries directly in Telegram by retrieving historical context from memory and executing a clean, time-limit-free general web search.

---

## Why Telegram?

While Slack and Line dominate internal corporate chat in Japan, we selected Telegram for two product-led reasons:
* **Frictionless Bot Interaction:** Unlike Slack, which requires admin approvals to install enterprise apps, any PM can search for our Telegram bot and start interacting instantly.
* **Native Rich Formatting & Broadcasting:** Telegram provides a native, cross-platform broadcasting interface with a robust HTML parsing engine, allowing us to deliver dense, color-coded visual tiers directly to a PM's mobile device.

---

## Value & User Impact

* **100% Trusted Links:** Click news sources with complete confidence. The self-healing URL resolver verifies headlines against search results, completely preventing LLM link hallucinations.
* **No Redundant Reading:** The title deduplicator filters out duplicate news coverage across feeds, ensuring PMs only review unique signals instead of reading the same story three times.
* **Retrospective Context:** Because daily digests persist in memory, on-demand queries combine live web searches with historical memory logs. This allows PMs to cross-reference fresh news with past signals (e.g., matching a new announcement against past local initiatives saved in memory).
* **Privacy Guardrails:** The pre-execution search filters block prompt injections and corporate PII from leaking to external search engine APIs.

---

## What Makes It Different

Four design decisions reflect real PM work in Japan that a generic agent would miss:

**Government ahead of enterprise.** Japan passed its first AI law in 2025, committed $65 billion to AI infrastructure through 2030, and framed the entire strategy as national recovery — the government has openly said Japan is behind. Policy moves here consistently precede enterprise adoption by 12–24 months, making them some of the most actionable signals a Japan PM can track.

**The Japan commitment lens.** OpenAI, Anthropic, and Cohere have Japan offices. Their model releases are gems — localization and enterprise sales follow. The classifier cross-references a handcrafted list of ~20 Japan-committed companies, so an English-first release gets scored on commitment, not language.

**Use cases abroad as leading indicators.** A German manufacturer deploying AI for predictive maintenance is noise for most PMs. For a Japan PM it's a gem — Japan's manufacturing sector is the likely next market, and the adoption lag makes it actionable today.

**Local Japanese AI labs as first-class signals.** NTT, Fujitsu, Sakana AI, and Preferred Networks are building models and infrastructure specifically for the Japanese market. The agent tracks these alongside global labs — a locally fine-tuned model that handles Japanese enterprise documents is often more actionable for a Japan PM than a frontier release from abroad.

---

## Course Concepts Applied

* **State & Workflow DAGs (ADK 2.0):** Built a multi-mode conditional routing workflow using ADK 2.0 context state and routing rules.
* **Asynchronous Triggers (Pub/Sub):** Connected the Telegram bot asynchronously to the FastAPI backend using Pub/Sub message envelopes to handle user queries.
* **Persistent Memory (Day 3):** Deployed a file-based storage layer to persist structured digests, enabling cross-session retrieval and Q&A memory context lookup.
* **Progressive Disclosure via Agent Skills (Day 3):** Packaged Japan-specific policy and vertical rules as a dynamic Agent Skill, preventing context window rot during processing.
* **Security Hook Gates (Day 4):** Configured `hooks.json` pre-execution script hooks to validate search inputs and abort unsafe API tool calls.
* **LLM-as-a-Judge Evaluation (Day 4):** Created a 12-case evaluation dataset and judge instructions to grade the agent on taxonomy classification and security.
