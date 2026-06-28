# PM AI Signal Tracker — Architecture Spec
# Source of truth for all design decisions.
# Last updated: 2026-06-28 (post Antigravity self-healing & Q&A updates)

---

## Three Operating Modes

### 1. `digest`
**Trigger:** Cloud Scheduler at 9am JST → Pub/Sub message `{"trigger": "digest"}`
**Workflow:** prepare_digest_queries → classifier → route_by_gem_score → digest_formatter → store_and_finish
**Console:** Same structured digest as Telegram
**Telegram:** ONE message, HTML parse mode, built deterministically from classified_signals JSON
  Structure:
  - 📊 PM AI Signal Tracker — [DATE]
  - Executive summary (2-3 sentences from digest_formatter — naturally short by design)
  - 🔴 Must-Read (Gem 5): max 2 signals, full card
  - 🟠 Watch Closely (Gem 4): max 3 signals, full card
  - 🟡 On the Radar (Gem 3): max 3 signals, headline + japan_angle + source only
  - ⚪ Background (Gem 1-2): max 3 signals, headline only
  - Empty tier → "No Gem X signals today."
  - NO splitting. ONE message always. If it doesn't fit, reduce signal caps.

### 2. `monitor`
**Trigger:** Cloud Scheduler every 3h → Pub/Sub message `{"trigger": "monitor"}`
**Workflow:** prepare_digest_queries → classifier → route_by_gem_score → monitor_finish (@node)
**Console:**
  - If breaking=True signal found: "⚡ Breaking signal found: [headline]"
  - If no breaking=True signal: "✅ Nothing important in the last 2 hours. Next scan coming."
**Telegram:**
  - If breaking=True signal found: ONE combined message, max 3 signals, built deterministically
    Format: 🚨 BREAKING — [DATE]\n\n1. [headline]\n🇯🇵 [japan_angle]\n🔗 [url]\n\n2. ...
  - If no breaking=True signal: NO Telegram message
  Note: breaking=True check, NOT gem_score=5 check — these are orthogonal

### 3. `query` (on-demand Q&A)
**Trigger:** User messages Telegram bot → polling loop (`app/telegram_poll.py`)
  publishes Pub/Sub message `{"trigger": "query", "question": "..."}`
**Workflow:** on_demand_router → after_on_demand_router → classifier → route_by_gem_score → query_formatter → store_and_finish
**Console:** Brief Q&A answer (same as Telegram reply)
**Telegram:** ONE reply message
  - 2-3 sentence direct answer
  - Most relevant signal: headline + japan_angle + source
  - Second signal only if genuinely relevant
  - NO gem tier listing, NO "No Gem 5 today"
  - Naturally short by design

---

## Workflow Routing

```
START → detect_trigger

detect_trigger sets delivery_mode in state and routes directly:
  "scan"   → prepare_digest_queries (for "digest" and "monitor" modes)
  "query"  → on_demand_router (for "query" mode)

prepare_digest_queries (@node) → classifier
on_demand_router (LlmAgent) → after_on_demand_router → classifier

classifier → route_by_gem_score

route_by_gem_score reads delivery_mode, yields route=delivery_mode:
  yield Event(output=node_input, state=..., route=ctx.state['delivery_mode'])

  "digest"  → digest_formatter (LlmAgent) → store_and_finish → END
  "monitor" → monitor_finish (@node, no LLM) → END
  "query"   → query_formatter (LlmAgent) → store_and_finish → END
```

Edges definition:
```python
(route_by_gem_score, {
    "digest": digest_formatter,
    "monitor": monitor_finish,
    "query": query_formatter,
})
```

---

## Search & Input Deduplication Strategy

To prevent API cost/latency bloat, search execution is offloaded to pure Python nodes. The LlmAgent `classifier` remains a pure classification node.

### 1. scheduled (digest/monitor) path
* Runs 8 searches concurrently via `ThreadPoolExecutor` (4 English + 4 Japanese).
* **Bilingual Title-Similarity Deduplicator:** A Python helper (`_deduplicate_articles`) parses Kanji/Katakana and English keywords. If an article shares $>55\%$ keywords with an already seen article, it is discarded to prevent duplicate signals of the same news story.
* Filters out results older than 24h (`hours=24`).
* Suffixes like `{month}` are **omitted** to ensure query freshness.

### 2. on-demand (query) path
* **Conversational Query Cleaning:** `_clean_query_for_search` strips punctuation and conversational prefixes (e.g. converting `"how about helm.ai?"` to `"helm.ai"`) in Python before querying.
* **Organic Web Search:** Uses general Google Web search (`news_only=False`) and **bypasses the 24-hour limit** (`time_limit=None`) to guarantee rich result pages for private startups or general topics.

---

## URL Resolution & Self-Healing Matching

To prevent URL hallucinations, Python maps search results to the LLM's classification output in `route_by_gem_score`.

1. **Pydantic Extract Hook (`_extract_signals`):** Unpacks the classified signals list safely, resolving Pydantic model vs dictionary type serialization mismatches.
2. **Weighted Keyword Matching:**
   * Specific keywords (capitalized words excluding the first, plus numbers) receive a weight of **`5`**.
   * Japanese-to-English synonyms (e.g., mapping `"防衛"` in the Japanese title to `"defense"` in the headline) receive a weight of **`3`**.
   * Generic words get a weight of **`1`**. Generic search query terms (like `"japan"`, `"ai"`) are ignored.
3. **Threshold Check:** Python calculates matches for all articles. It only trusts the LLM's suggested index if its score is close (within 3 points) to the maximum score. If the suggested index is significantly worse (e.g., matching a generic article instead of the specific proper noun), Python overrules the ID and self-heals the URL to the best-matching article.

---

## Breaking Signal Rules

- `breaking: bool` field on SignalCategory Pydantic schema
- Set by classifier only when: gem_score=5 AND published last 2h AND market-shifting event
- Expected frequency: 0-1 per week
- breaking=True requires gem_score=5 — never breaking without gem 5
- gem_score=5 without breaking=True → appears in digest only, no proactive alert
- monitor_finish checks breaking=True explicitly, NOT has_gem_5
- Multiple breaking in one monitor run → ONE combined Telegram message, max 3 signals

---

## Three Separate LlmAgents

One LlmAgent per output type. No conditional branching inside a single agent.

* **digest_formatter:** Produces executive summary only (2-3 sentences). Output key: `executive_summary`. Temp: 0.2.
* **query_formatter:** Produces brief Q&A answer. Output key: `query_answer`. Temp: 0.2.
* **on_demand_router:** Retrieves memory contexts and searches relevant history to pass to `after_on_demand_router`.

All use `gemini-2.5-flash`.

---

## ADK 2.0 Event Contract

All workflow nodes trigger and pass outputs using ADK 2.0's strict `Event(output=...)` signature (avoiding `Event(data=...)` which is ignored by the Pydantic parser, causing empty inputs).

---

## Implementation Status

### Completed ✅
- **ADK 2.0 Event outputs:** Switched all nodes from `data=` to `output=` to pass inputs cleanly.
- **Pydantic Model Extractors:** Created `_extract_signals` to handle type coercion safely.
- **Bilingual Title Deduplicator:** Stops duplicate articles from creating duplicate signals in digest.
- **Q&A Organic Web Search:** Cleans queries and searches web pages without time limits for on-demand query.
- **Self-Healing Weighted URL Matcher:** Evaluates proper nouns, numbers, and cross-lingual synonyms to align URLs with 100% precision.
- **Three operating modes:** Tested end-to-end (digest ✅ monitor ✅ query ✅).
- **Cleaned print logs:** Checked for diagnostic clutter; only required tracing logs remain.
- **Eval Dataset:** Updated `tests/eval/datasets/signals-dataset.json` to define the 12 spec scenarios.
- **Unit & Integration Tests:** Updated `tests/test_agent.py` to fix imports and deprecated test cases (all 24 tests passing).

### Remaining ⏳
- [ ] Final writeup update
- [ ] Push to GitHub
- [ ] Record video demo
- [ ] Submit to Kaggle before July 6
