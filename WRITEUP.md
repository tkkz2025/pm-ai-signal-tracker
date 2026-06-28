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

---

## Why Telegram?

We chose Telegram as our primary delivery channel for two reasons:
* **Native Cross-Platform Accessibility:** Telegram is a widely adopted messenger that works seamlessly across mobile, desktop, and web, making it easy to check updates on any device.
* **Built for News & Broadcasting:** Telegram is exceptionally well-suited for news digests and broadcast streams due to its native channel architecture, providing a clean, distraction-free environment for PMs to scan insights.

---

## Value & User Impact

* **100% Trusted Links:** The self-healing URL resolver prevents LLM link hallucinations, meaning PMs can click news sources with complete confidence.
* **No Redundant Reading:** The title deduplicator filters out duplicate news coverage across feeds, ensuring PMs only review unique signals instead of reading the same story three times.
* **Retrospective Search:** Because memory persists across sessions, the Telegram bot acts as a searchable database of Japan's AI signal history over time, not just a temporary alert feed.
* **Privacy Guardrails:** The pre-execution search filters block prompt injections and corporate PII from leaking to external search engine APIs.

---

## What Makes It Different

Four design decisions reflect real PM work in Japan that a generic agent would miss:

**Government ahead of enterprise.** Japan passed its first AI law in 2025, committed $65 billion to AI infrastructure through 2030, and framed the entire strategy as national recovery — the government has openly said Japan is behind. Policy moves here consistently precede enterprise adoption by 12–24 months, making them some of the most actionable signals a Japan PM can track.

**The Japan commitment lens.** OpenAI, Anthropic, and Cohere have Japan offices. Their model releases are gems — localization and enterprise sales follow. The classifier cross-references a handcrafted list of ~20 Japan-committed companies, so an English-first release gets scored on commitment, not language.

**Use cases abroad as leading indicators.** A German manufacturer deploying AI for predictive maintenance is noise for most PMs. For a Japan PM it's a gem — Japan's manufacturing sector is the likely next market, and the adoption lag makes it actionable today.

**Local Japanese AI labs as first-class signals.** NTT, Fujitsu, Sakana AI, and Preferred Networks are building models and infrastructure specifically for the Japanese market. The agent tracks these alongside global labs — a locally fine-tuned model that handles Japanese enterprise documents is often more actionable for a Japan PM than a frontier release from abroad.

---

## How It Works (Course Concepts Applied)

* **State & Workflow Orchestration:** Uses ADK 2.0 conditional routing to orchestrate distinct classification, formatting, and retrieval steps based on user triggers.
* **Persistent Memory:** Persists structured digests in long-term memory so Q&A queries can perform retrospective analysis over past weeks.
* **Asynchronous Pub/Sub Integration:** Connects the Telegram interface with the FastAPI server asynchronously using Pub/Sub message envelopes.
* **Pre-Execution Security Hooks:** Blocks prompt injections and personal identifiers in queries before they are sent to third-party search APIs.
* **Bilingual Search & Self-Healing Links:** Aggregates Japanese and English searches, deduplicates identical news coverage, and programmatically verifies and repairs URL links in Python.
* **Rigorous Domain Grading:** Grades the agent using unit tests and an LLM-as-a-judge dataset representing realistic PM scenarios.
