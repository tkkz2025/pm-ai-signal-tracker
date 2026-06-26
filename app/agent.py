"""
PM AI Signal Tracker
====================
Monitors global AI news daily and surfaces strategic signals
for product managers working on AI products in Japan.

Two entry points:
  1. Scheduled digest  — autonomous daily run, fetches last 24h AI news
  2. On-demand query   — user asks a question, retrieves from memory + live search

Workflow:
  START → detect_trigger → [scheduled: prepare_digest_queries | on_demand: on_demand_router]
        → classifier (LlmAgent) → route_by_gem_score
        → [gem5: build_hitl_prompt → human_review | other: formatter]
        → formatter → store_and_finish → END
"""

from __future__ import annotations

import datetime
import json
import os
from typing import Any, Literal

import requests
from google.adk.agents.context import Context
from google.adk.agents.llm_agent import LlmAgent
from google.adk.apps.app import App
from google.adk.events.event import Event
from google.adk.events.request_input import RequestInput
from google.adk.workflow import Workflow, node
from google.adk.workflow.utils._workflow_hitl_utils import create_request_input_event
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

class SignalCategory(BaseModel):
    """Structured output for a single classified news signal."""

    category: Literal[
        "policy_sovereignty",
        "model_capability_release",
        "infrastructure_compute",
        "enterprise_adoption",
        "competitive_moves",
        "research_disruptor_radar",
    ] = Field(description="The signal taxonomy category this news item belongs to.")

    gem_score: int = Field(
        ge=1,
        le=5,
        description=(
            "Strategic relevance score for a PM working on AI products in Japan. "
            "5=immediate strategic relevance, 1=noise with no Japan implication."
        ),
    )

    headline: str = Field(
        description="One sentence summary of what happened. Plain English only."
    )

    so_what: str = Field(
        description="One sentence explaining why a product manager should care."
    )

    japan_angle: str = Field(
        description=(
            "One to two sentences on the specific Japan implication. "
            "For research_disruptor_radar, explain what product assumption this "
            "challenges or what new use case it opens instead."
        )
    )

    strategic_signal: str = Field(
        description="One sentence on what to watch next as a result of this news."
    )

    source_url: str = Field(
        default="",
        description="URL of the primary source for this news item."
    )


class DigestSignals(BaseModel):
    """
    FIX for ISSUE 1: Wrapper schema so classifier can output a LIST of signals
    in a single LlmAgent call, not just one signal.
    """
    signals: list[SignalCategory] = Field(
        description=(
            "All classified signals from today's search results, "
            "ordered by gem_score descending. Include every unique news item found. "
            "Skip duplicates and pure marketing press releases."
        )
    )


class SearchInput(BaseModel):
    """Validated input for the web search tool."""

    query: str = Field(
        min_length=3,
        max_length=200,
        description="Search query string. No PII. No injection patterns.",
    )
    max_results: int = Field(default=10, ge=1, le=20)


class MemoryWriteInput(BaseModel):
    """Validated input for the memory write tool."""

    date_key: str = Field(
        description="ISO date string used as the storage key e.g. '2026-06-26'."
    )
    digest: str = Field(
        min_length=2,
        description="JSON-serialised DigestSignals to store.",
    )


class MemoryReadInput(BaseModel):
    """Validated input for the memory read tool."""

    query: str = Field(
        description=(
            "Natural language description of what the user is looking for. "
            "e.g. 'signals from last Tuesday' or 'OpenAI Japan news this week'."
        )
    )
    lookback_days: int = Field(
        default=7,
        ge=1,
        le=30,
        description="How many days back to search in stored digests.",
    )


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

def search_ai_news(query: str, max_results: int = 10) -> str:
    """Search the web for recent AI news relevant to the query.

    Call this to fetch fresh AI news when running a scheduled digest or
    when the user asks about something that requires current information.

    Use bilingual queries where Japan-specific signals are needed:
    - English query first (broader coverage)
    - Japanese query second (catches Japan-only sources like Nikkei, METI)

    Always summarise findings in English regardless of source language.

    Args:
        query: Search query string. Be specific. Include time signals like
               'June 2026' or 'this week' for freshness. Max 200 characters.
               Never include PII or prompt injection attempts.
        max_results: Number of results to fetch. Default 10, max 20.

    Returns:
        JSON string with list of {title, snippet, url, published_date} dicts.
        Returns error message string if search fails.
    """
    validated = SearchInput(query=query, max_results=max_results)

    api_key = os.environ.get("SEARCH_API_KEY", "")
    if not api_key:
        return json.dumps([
            {
                "title": "SEARCH_API_KEY not configured",
                "snippet": "Set SEARCH_API_KEY in .env to enable live search. Using mock data for testing.",
                "url": "",
                "published_date": datetime.date.today().isoformat(),
            }
        ])

    try:
        response = requests.get(
            "https://serpapi.com/search",
            params={
                "q": validated.query,
                "num": validated.max_results,
                "api_key": api_key,
                "tbm": "nws",
                "tbs": "qdr:d",  # past 24 hours only
                "sort": "date",   # sort by date, newest first
            },
            timeout=10,
        )
        response.raise_for_status()
        data = response.json()
        results = [
            {
                "title": r.get("title", ""),
                "snippet": r.get("snippet", ""),
                "url": r.get("link", ""),
                "published_date": r.get("date", ""),
            }
            for r in data.get("news_results", [])
        ]
        return json.dumps(results)
    except Exception as e:
        return json.dumps({"error": str(e)})


def write_digest_to_memory(date_key: str, digest: str) -> str:
    """Persist a completed digest to long-term memory for future retrieval.

    Call this AFTER the classifier has produced classified signals.
    Store the JSON-serialised DigestSignals, not the formatted markdown output.
    Must be called once per digest run so on-demand queries can reference
    past signals.

    Args:
        date_key: ISO date string e.g. '2026-06-26'. Used as the lookup key.
        digest: JSON-serialised DigestSignals string. Must be valid JSON.

    Returns:
        Confirmation string with the date_key that was stored, or error message.
    """
    validated = MemoryWriteInput(date_key=date_key, digest=digest)

    memory_dir = ".agents/memory"
    os.makedirs(memory_dir, exist_ok=True)
    path = os.path.join(memory_dir, f"{validated.date_key}.json")

    try:
        json.loads(validated.digest)  # validate before storing
        with open(path, "w", encoding="utf-8") as f:
            f.write(validated.digest)
        return f"Stored digest for {validated.date_key} at {path}."
    except json.JSONDecodeError as e:
        return f"Error: digest is not valid JSON — {e}"
    except OSError as e:
        return f"Error writing to memory: {e}"


def read_digests_from_memory(query: str, lookback_days: int = 7) -> str:
    """Retrieve past digests from long-term memory to answer on-demand queries.

    Call this when the user asks about past signals, trends, or wants to
    compare today's news to a previous period.

    Args:
        query: Natural language description of what to look for.
               e.g. 'OpenAI Japan signals this week' or 'gem score 5 signals'.
        lookback_days: How many days back to search. Default 7, max 30.

    Returns:
        JSON string with list of matching DigestSignals objects from memory.
        Returns empty list JSON if no matching digests found.
    """
    validated = MemoryReadInput(query=query, lookback_days=lookback_days)

    memory_dir = ".agents/memory"
    if not os.path.exists(memory_dir):
        return json.dumps([])

    cutoff = datetime.date.today() - datetime.timedelta(days=validated.lookback_days)
    results = []

    try:
        for filename in sorted(os.listdir(memory_dir), reverse=True):
            if not filename.endswith(".json"):
                continue
            date_str = filename.replace(".json", "")
            try:
                file_date = datetime.date.fromisoformat(date_str)
            except ValueError:
                continue
            if file_date < cutoff:
                continue
            path = os.path.join(memory_dir, filename)
            with open(path, "r", encoding="utf-8") as f:
                results.append(json.load(f))

        return json.dumps(results)
    except OSError as e:
        return json.dumps({"error": str(e)})


# ---------------------------------------------------------------------------
# Function nodes
# ---------------------------------------------------------------------------

@node
def detect_trigger(ctx: Context, node_input: Any):
    """Detect whether this run is a scheduled digest or an on-demand query.

    Writes 'trigger' and 'user_query' to ctx.state and routes accordingly.
    Scheduled runs arrive with empty, 'scheduled', or 'run digest' input.
    On-demand queries arrive with a natural language question string.

    ADK may wrap the input as a dict, Content object, or plain string —
    this node extracts the raw text regardless of wrapping.
    """
    # Extract plain text from whatever ADK passes in
    raw = node_input

    # Handle Content objects (ADK web UI wraps messages this way)
    if hasattr(raw, 'parts'):
        parts = raw.parts or []
        raw = " ".join(p.text for p in parts if hasattr(p, 'text') and p.text)
    elif isinstance(raw, dict):
        # Handle {'parts': [{'text': '...'}]} dict form
        parts = raw.get('parts', [])
        if parts:
            raw = " ".join(
                p.get('text', '') for p in parts if isinstance(p, dict)
            )
        else:
            raw = raw.get('text', str(node_input))

    trigger_input = str(raw).strip().lower()

    is_scheduled = (
        not trigger_input
        or trigger_input == "scheduled"
        or trigger_input == "run digest"
        or trigger_input == "digest"
    )

    trigger = "scheduled" if is_scheduled else "on_demand"
    yield Event(
        data=raw,
        state={"trigger": trigger, "user_query": str(raw)},
        route=trigger,
    )


@node
def prepare_digest_queries(ctx: Context, node_input: Any):
    """Prepare bilingual search queries for a scheduled digest run.

    Generates English + Japanese query pairs per signal category for
    broad source coverage. Stores queries in ctx.state['search_queries'].
    """
    today = datetime.date.today().isoformat()
    month = today[:7]  # e.g. '2026-06'

    queries = [
        f"Japan AI policy METI government regulation {month}",
        f"AI national strategy data sovereignty {month}",
        f"new AI model release benchmark {month}",
        f"OpenAI Anthropic Google AI Japan office {month}",
        f"Japan data center AI compute infrastructure {month}",
        f"Rapidus semiconductor TSMC Kumamoto AI {month}",
        f"AI enterprise deployment manufacturing healthcare Japan {month}",
        f"AI use case global manufacturing retail finance {month}",
        f"AI company partnership acquisition Japan SoftBank NTT {month}",
        f"AI research paper product implication use case {month}",
    ]

    yield Event(
        data=json.dumps(queries),  # pass as JSON string to classifier
        state={"search_queries": queries, "run_date": today},
    )


@node
def route_by_gem_score(ctx: Context, node_input: Any):
    """Route gem score 5 signals to human review; all others go to formatter.

    FIX for ISSUE 2: classified_signals is stored by ADK as a dict
    (Pydantic model serialised to dict via output_schema). Access signals
    list from the DigestSignals wrapper dict.
    """
    classified = ctx.state.get("classified_signals", {})

    # DigestSignals wrapper stores signals under 'signals' key
    if isinstance(classified, dict):
        signals_list = classified.get("signals", [])
    else:
        signals_list = []

    has_gem_5 = any(
        (s.get("gem_score", 0) if isinstance(s, dict) else 0) == 5
        for s in signals_list
    )

    route = "human_review" if has_gem_5 else "format_output"
    yield Event(data=node_input, state={"has_gem_5": has_gem_5}, route=route)


@node
def build_hitl_prompt(ctx: Context, node_input: Any):
    """HITL node: pauses workflow and requests human confirmation for gem 5 signals.

    Writes signals to a temp file BEFORE the interrupt so the formatter
    can read them after ADK resets state on resume.
    """
    classified = ctx.state.get("classified_signals", {})
    signals_list = classified.get("signals", []) if isinstance(classified, dict) else []

    gem_5_signals = [
        s for s in signals_list
        if isinstance(s, dict) and s.get("gem_score", 0) == 5
    ]

    signals_text = json.dumps(gem_5_signals, indent=2, ensure_ascii=False)

    # Write ALL signals to temp file BEFORE yielding RequestInput
    # This survives ADK state reset on resume
    tmp_dir = ".agents/memory"
    os.makedirs(tmp_dir, exist_ok=True)
    tmp_path = os.path.join(tmp_dir, "_hitl_pending.json")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump({
            "classified_signals": classified,
            "trigger": ctx.state.get("trigger", "on_demand"),
            "run_date": ctx.state.get("run_date", datetime.date.today().isoformat()),
        }, f, ensure_ascii=False)

    message = (
        "⚡ HIGH-PRIORITY SIGNAL DETECTED (Gem Score 5)\n\n"
        f"{signals_text}\n\n"
        "Include this in your digest? Reply: yes / no / edit"
    )

    yield create_request_input_event(RequestInput(message=message))

    # After resume, re-load from file and restore state
    try:
        with open(tmp_path, "r", encoding="utf-8") as f:
            saved = json.load(f)
        yield Event(
            data="hitl_approved",
            state={
                "hitl_confirmed": True,
                "classified_signals": saved["classified_signals"],
                "trigger": saved["trigger"],
                "run_date": saved["run_date"],
            },
        )
    except Exception as e:
        yield Event(data="hitl_approved", state={"hitl_confirmed": True})


@node
def after_on_demand_router(ctx: Context, node_input: Any):
    """
    FIX for ISSUE 5: LlmAgents cannot emit route= Events.
    This @node bridges on_demand_router → classifier by:
    1. Reading on_demand_router output from ctx.state['routed_query']
    2. FIX for ISSUE 4: Normalising ctx.state key to 'search_queries'
       so classifier instruction works identically on both paths.
    """
    routed = ctx.state.get("routed_query", "")
    today = datetime.date.today().isoformat()

    # on_demand_router may have already called search tools and stored results.
    # Store under search_queries so classifier instruction finds them consistently.
    existing_results = ctx.state.get("search_results", [])

    yield Event(
        data=routed,
        state={
            "search_queries": [],          # empty — on_demand_router already searched
            "search_results": existing_results,
            "run_date": today,
        },
        route="to_classifier",
    )


@node
def store_and_finish(ctx: Context, node_input: Any):
    """Store classified signals to memory and emit final response.

    Before storing, deduplicates signals against yesterday's digest
    so repeat stories don't appear in consecutive daily digests.
    """
    classified = ctx.state.get("classified_signals", {})
    run_date = ctx.state.get("run_date", datetime.date.today().isoformat())

    signals = classified.get("signals", []) if isinstance(classified, dict) else []

    # Deduplication: load yesterday's signals and filter out repeats
    try:
        yesterday = (
            datetime.date.fromisoformat(run_date) - datetime.timedelta(days=1)
        ).isoformat()
        yesterday_path = os.path.join(".agents/memory", f"{yesterday}.json")
        if os.path.exists(yesterday_path):
            with open(yesterday_path, "r", encoding="utf-8") as f:
                yesterday_data = json.load(f)
            past_headlines = {
                s.get("headline", "").lower().strip()
                for s in yesterday_data.get("signals", [])
            }
            past_urls = {
                s.get("source_url", "").strip()
                for s in yesterday_data.get("signals", [])
                if s.get("source_url", "").strip()
            }
            before_count = len(signals)
            signals = [
                s for s in signals
                if s.get("headline", "").lower().strip() not in past_headlines
                and s.get("source_url", "").strip() not in past_urls
            ]
            removed = before_count - len(signals)
            if removed:
                print(f"[dedup] Removed {removed} signals already seen yesterday.")
    except Exception as e:
        print(f"[dedup] Skipped deduplication: {e}")

    digest_to_store = json.dumps({
        "run_date": run_date,
        "trigger": ctx.state.get("trigger", "scheduled"),
        "signals": signals,
    }, ensure_ascii=False)

    write_result = write_digest_to_memory(
        date_key=run_date,
        digest=digest_to_store,
    )

    formatted = ctx.state.get("formatted_digest", "")
    yield Event(
        data=f"{formatted}\n\n---\n_Digest stored: {write_result}_",
        state={"stored": True},
    )


def load_hitl_pending() -> str:
    """Load signals saved before a HITL interrupt from the pending file.

    Call this when ctx.state['classified_signals'] is empty after a
    human-in-the-loop confirmation, to recover the signals that were
    saved before the interrupt.

    Returns:
        JSON string with classified_signals dict, or empty dict if not found.
    """
    tmp_path = os.path.join(".agents/memory", "_hitl_pending.json")
    try:
        if os.path.exists(tmp_path):
            with open(tmp_path, "r", encoding="utf-8") as f:
                return f.read()
        return json.dumps({})
    except Exception as e:
        return json.dumps({"error": str(e)})


# ---------------------------------------------------------------------------
# LLM nodes
# ---------------------------------------------------------------------------

classifier = LlmAgent(
    name="classifier",
    model="gemini-2.5-flash",  # switched from flash-lite due to 503 capacity issues
    output_key="classified_signals",
    output_schema=DigestSignals,
    tools=[search_ai_news],
    instruction="""You are a signal classifier for a PM AI Signal Tracker.
Your job is to search for AI news and classify each item into strategic
signals for product managers working on AI products in Japan.

CRITICAL: You MUST always call search_ai_news at least once before
producing output. Never respond with prose — always produce a
DigestSignals JSON object with a 'signals' list.
Never return an empty signals list if search results were found.

SCHEDULED RUN (ctx.state['trigger'] == 'scheduled'):
Run ALL of these searches using search_ai_news, one at a time:
1. "Japan AI policy METI 2026"
2. "new AI model release Japan 2026"
3. "AI enterprise deployment Japan manufacturing 2026"
4. "AI company Japan partnership SoftBank OpenAI 2026"
5. "AI research product disruption 2026"

ON-DEMAND RUN (ctx.state['trigger'] == 'on_demand'):
The on_demand_router has already searched and its summary is available
as your input context. Use that context PLUS call search_ai_news once
with ctx.state['user_query'] for any additional fresh results.
Classify everything relevant you find into signals.

---

SIGNAL CATEGORIES — pick exactly one per news item:

1. policy_sovereignty
   Laws, AI strategies, data residency rules, safety frameworks.
   Japan filter: METI directives, AI Strategy Council, "AI Nippon" updates,
   data localisation rulings, sovereign compute policy.

2. model_capability_release
   New model launches, benchmark jumps, open-source releases.
   Japan filter — BOTH lenses:
   - COMMITMENT LENS: English-first is NOT noise if company has Japan
     presence (OpenAI Japan, Anthropic Japan, Cohere, Google Japan,
     Microsoft Azure Japan, AWS Japan). Their releases are gems.
   - CAPABILITY LENS: Japanese-native models (NTT Tsuzumi, Fujitsu Kozuchi,
     SoftBank AI, Sakana AI). Benchmark jumps in document processing,
     reasoning, multimodal.

3. infrastructure_compute
   Cloud expansions, chip supply chain, data centres, energy constraints.
   Japan filter: AWS/Azure/Google DC builds in Japan, Rapidus semiconductor,
   TSMC Kumamoto fab.

4. enterprise_adoption
   Who is deploying AI and with what outcome — anywhere in the world.
   Japan filter — TWO lenses:
   - DOMESTIC: Japanese enterprise deployments, Keidanren members.
   - GLOBAL USE CASE SCOUTING: Proven deployments abroad in Japan's key
     verticals (manufacturing, healthcare, retail, finance, public sector,
     telco). A proven global use case = 12-18 month Japan leading indicator.
     These are gems regardless of geography.

5. competitive_moves
   M&A, product launches, pricing, partnerships from major AI players.
   Japan filter: SoftBank/OpenAI, NTT-Docomo AI, Sony AI, Rakuten AI.
   Watch for foreign AI companies forming KK or GK entities in Japan.

6. research_disruptor_radar
   Papers, evals, safety findings — filtered by ONE question:
   Does this create or destroy a product assumption, open a new use case,
   or change who can build what?
   Disruptor lens: capability jumps killing existing assumptions, methods
   lowering barrier for local Japanese model building, safety findings in
   regulated verticals (medical, financial).
   Emerging use case lens: new product categories Japan will care about.

---

GEM SCORING RUBRIC:
5 — Immediate strategic relevance to Japan AI product decisions this week
4 — Strong Japan relevance, actionable in 3-6 months
3 — Indirect Japan relevance, worth tracking as trend
2 — Globally interesting, low Japan near-term impact
1 — Noise: no product implication, no Japan relevance

---

FEW-SHOT EXAMPLES:

Example 1:
News: "Anthropic opens Tokyo office and announces Japanese enterprise support"
Output signal:
  category: competitive_moves
  gem_score: 5
  headline: Anthropic established a Tokyo office with dedicated Japanese enterprise support.
  so_what: A top-3 frontier AI lab is now locally present in Japan, accelerating Claude adoption in Japanese enterprise.
  japan_angle: Local presence enables Japanese companies to sign enterprise contracts with in-country support and compliance. Expect NDA-first Japanese enterprise deals to accelerate in 6-12 months.
  strategic_signal: Watch for Anthropic Japan partnerships with Keidanren members in manufacturing and financial services.

Example 2:
News: "Stanford paper shows LLMs can process 10M token context reliably"
Output signal:
  category: research_disruptor_radar
  gem_score: 4
  headline: Stanford research demonstrates reliable 10M token context in LLMs.
  so_what: This invalidates the assumption that enterprise document workflows require RAG pipelines.
  japan_angle: Japanese enterprises run on document-heavy workflows (contracts, ringi approvals, regulatory filings). Long-context reliability opens direct AI product opportunities without complex RAG infrastructure.
  strategic_signal: Watch for major model providers updating context window limits and RAG-based startups to pivot.

Example 3:
News: "OpenAI raises $5B in new funding round"
Output signal:
  category: competitive_moves
  gem_score: 2
  headline: OpenAI secured $5B in additional funding.
  so_what: Extended runway may accelerate OpenAI's product roadmap and Japan market expansion.
  japan_angle: No immediate Japan impact but sustained investment supports the SoftBank partnership and eventual Japanese enterprise feature prioritisation.
  strategic_signal: Monitor for Japan-specific product or partnership announcements in the next quarter.

---

HARD RULES:
- Output English only. Never output Japanese text in any field.
- Never invent company names, partnerships, or facts not in search results.
- Classify each unique news story only once. Skip duplicates.
- Skip pure marketing press releases with no product or policy substance.
- Never score gem 4-5 without a specific, concrete Japan implication.
- RECENCY: Only classify news published in the last 24-48 hours.
  Check the published_date field. Skip anything older than 2 days.
  If no date is available, use your judgment — skip if it feels like old news.
- MAX OUTPUT: Return at most 15 signals total. If you find more,
  keep the highest gem-score ones and drop the rest.
""",
)


formatter = LlmAgent(
    name="formatter",
    model="gemini-2.5-flash",
    output_key="formatted_digest",
    tools=[read_digests_from_memory, load_hitl_pending],
    instruction=f"""You are the PM-lens formatter for the PM AI Signal Tracker.

TODAY'S DATE IS: {datetime.date.today().isoformat()}
Always use this exact date in the digest header. Never use any date from
article content, search results, or news snippets.

CRITICAL: Never ask the user for input. Never ask clarifying questions.
Always produce a formatted digest. Follow this exact order:
1. Check ctx.state['classified_signals'] — if it has signals, use them.
2. If classified_signals is empty or missing, call load_hitl_pending() to
   recover signals saved before the HITL interrupt.
3. If still no signals, call read_digests_from_memory with today's date.
4. Only say "No signals found today" if ALL three sources return nothing.

Your job is NOT to summarise the news. Make strategic implications
visible and actionable for a PM working on AI products in Japan.

TRIGGER TYPE is in ctx.state['trigger']:
- 'scheduled': Produce the full daily digest using the format below.
- 'on_demand': The user's question is in ctx.state['user_query'].
  FIRST: Write a 2-3 sentence direct answer to the user's specific question.
  THEN: Use read_digests_from_memory to check past signals.
  THEN: Present only signals directly relevant to the question.
  Do NOT produce a full digest — stay focused on what was asked.

---

OUTPUT FORMAT:

## PM AI Signal Tracker — [DATE]

### Executive Summary
[2-3 sentences on the most important strategic theme across gem 4-5
signals today. Reference specific companies or events — no vague trends.]

---

### 🔴 Must-Read Signals (Gem 5)
[All gem_score 5 signals using card format. If none, say "No Gem 5 signals today."]

### 🟠 Watch Closely (Gem 4)
[All gem_score 4 signals using card format]

### 🟡 On the Radar (Gem 3)
[All gem_score 3 signals using card format]

### ⚪ Background Noise (Gem 1-2)
[One-liner per signal — no full card]

---

SIGNAL CARD FORMAT:

**[EMOJI] [HEADLINE]**
So what: [so_what]
Japan angle: [japan_angle]
Watch next: [strategic_signal]
Source: [source_url]

CATEGORY EMOJIS:
🏛️ policy_sovereignty
🧠 model_capability_release
🏗️ infrastructure_compute
🏢 enterprise_adoption
⚔️ competitive_moves
🔬 research_disruptor_radar

---

HARD RULES:
- Output English only. Never output Japanese text.
- Never invent signals not in ctx.state['classified_signals'].
- Keep each signal card under 80 words (excluding source).
- For on_demand queries, lead with a direct answer before signals.
- MAX SIGNALS: Show at most 3 gem-5, 3 gem-4, 3 gem-3, 5 gem-1/2 signals.
  If more exist, pick the most Japan-relevant ones and drop the rest.
- Total digest should be readable in 5 minutes — trim ruthlessly.
""",
)


on_demand_router = LlmAgent(
    name="on_demand_router",
    model="gemini-2.5-flash",  # switched from flash-lite for reliability
    output_key="routed_query",
    tools=[read_digests_from_memory, search_ai_news],
    instruction="""You are a retrieval tool for the PM AI Signal Tracker.

NEVER ask the user any questions. NEVER say "What are you looking for?"
NEVER engage in conversation. Just retrieve and summarise.

The user's query is in ctx.state['user_query']. Always do both:
1. Call read_digests_from_memory with the query to check past signals
2. Call search_ai_news with the query to fetch fresh results

Then write a brief summary of what you found. That is all.

If ctx.state['user_query'] is empty or unclear, search for
"Japan AI news today" as the default query.
""",
)


# ---------------------------------------------------------------------------
# Workflow
# ---------------------------------------------------------------------------

root_workflow = Workflow(
    name="pm_ai_signal_tracker",
    edges=[
        # Entry point
        ("START", detect_trigger),

        # Trigger routing — covers all cases explicitly
        (detect_trigger, {
            "scheduled": prepare_digest_queries,
            "on_demand": on_demand_router,
        }),
        (prepare_digest_queries, classifier),

        # On-demand path bridge
        (on_demand_router, after_on_demand_router),
        (after_on_demand_router, {
            "to_classifier": classifier,
        }),

        # Both paths converge at route_by_gem_score
        (classifier, route_by_gem_score),

        # HITL gate — covers all cases explicitly
        (route_by_gem_score, {
            "human_review": build_hitl_prompt,
            "format_output": formatter,
        }),
        (build_hitl_prompt, formatter),

        # Formatter -> store -> END
        (formatter, store_and_finish),
    ],
)

app = App(name="app", root_agent=root_workflow)