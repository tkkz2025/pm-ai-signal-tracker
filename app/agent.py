"""
PM AI Signal Tracker
====================
Monitors global AI news and surfaces strategic signals for PMs working on AI
products in Japan. Three operating modes delivered via Pub/Sub:

  digest  — full daily digest at 9am → Telegram
  monitor — background scan every 3h → Telegram only if breaking signal found
  query   — on-demand Q&A from Telegram bot → brief answer to Telegram

Workflow:
  START → detect_trigger
      → scan (digest/monitor): prepare_digest_queries → classifier → route_by_gem_score
      → query:                 on_demand_router → after_on_demand_router
                               → classifier → route_by_gem_score

  route_by_gem_score (reads delivery_mode):
      → digest:  digest_formatter → store_and_finish → END
      → monitor: monitor_finish → END
      → query:   query_formatter → store_and_finish → END

URL Design:
  Articles are formatted with [N] IDs. Classifier outputs article_id: N.
  route_by_gem_score looks up url_lookup[str(N)] → real URL from SerpApi.
  The LLM never constructs or outputs URLs — Python owns URL assignment.
"""

from __future__ import annotations

import concurrent.futures
import datetime
import html
import json
import os
import re
from typing import Any, Literal

import requests
from google.adk.agents.context import Context
from google.adk.agents.llm_agent import LlmAgent
from google.adk.apps.app import App
from google.adk.events.event import Event
from google.adk.workflow import Workflow, node
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

class SignalCategory(BaseModel):
    category: Literal[
        "policy_sovereignty",
        "model_capability_release",
        "infrastructure_compute",
        "enterprise_adoption",
        "competitive_moves",
        "research_disruptor_radar",
    ]
    gem_score: int = Field(ge=1, le=5)
    headline: str = Field(description="One sentence summary in English.")
    so_what: str = Field(description="One sentence why a PM should care.")
    japan_angle: str = Field(description="One sentence Japan-specific implication.")
    strategic_signal: str = Field(description="One sentence what to watch next.")
    breaking: bool = Field(
        default=False,
        description=(
            "True ONLY if gem_score=5 AND published last 2 hours AND market-shifting event. "
            "Never set breaking=True on a signal below gem_score=5."
        ),
    )
    article_id: str = Field(
        default="-1",
        description=(
            "The integer N from the [N] at the start of the source article, as a string. "
            "Example: if article starts with '[7]', output '7'. "
            "Output '-1' if you cannot identify the source article."
        ),
    )


class DigestSignals(BaseModel):
    signals: list[SignalCategory] = Field(
        description="All classified signals, ordered by gem_score descending. Max 15."
    )


class MemoryWriteInput(BaseModel):
    date_key: str
    digest: str = Field(min_length=2)


class MemoryReadInput(BaseModel):
    query: str
    lookback_days: int = Field(default=7, ge=1, le=30)


# ---------------------------------------------------------------------------
# Telegram helpers
# ---------------------------------------------------------------------------

def _telegram_post(text: str, label: str = "message") -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        print(f"[Telegram] Credentials not set — skipping {label}.")
        return
    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": text[:4096],
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            },
            timeout=10,
        )
        resp.raise_for_status()
        print(f"[Telegram] ✅ Sent {label}")
    except Exception as e:
        print(f"[Telegram] ❌ Failed to send {label}: {e}")


def _esc(t: Any) -> str:
    return html.escape(str(t or ""))


def _extract_signals(classified: Any) -> list:
    """Safely extract list of signals from dict, Pydantic model, or other formats."""
    if not classified:
        return []
    if isinstance(classified, dict):
        return classified.get("signals", [])
    if hasattr(classified, "signals"):
        sigs = classified.signals
        if isinstance(sigs, list):
            return [s.model_dump() if hasattr(s, "model_dump") else s for s in sigs]
        return sigs
    if hasattr(classified, "model_dump"):
        return classified.model_dump().get("signals", [])
    return []


_CAT_EMOJI = {
    "policy_sovereignty": "🏛️",
    "model_capability_release": "🧠",
    "infrastructure_compute": "🏗️",
    "enterprise_adoption": "🏢",
    "competitive_moves": "⚔️",
    "research_disruptor_radar": "🔬",
}


def _build_digest_html(signals: list, run_date: str, executive_summary: str = "") -> str:
    """Build Telegram-safe HTML digest. Single source of truth for console + Telegram."""
    TIER_CAPS = {5: 2, 4: 3, 3: 3}
    tiers: dict[int, list] = {5: [], 4: [], 3: [], 2: [], 1: []}
    for s in signals:
        if isinstance(s, dict):
            score = s.get("gem_score", 1)
            if score in tiers and len(tiers[score]) < TIER_CAPS.get(score, 3):
                tiers[score].append(s)

    lines = [f"📊 <b>PM AI Signal Tracker — {_esc(run_date)}</b>", ""]

    if executive_summary:
        lines += [_esc(executive_summary.strip()), ""]

    tier_defs = [
        (5, "🔴 <b>Must-Read (Gem 5)</b>", "No Gem 5 signals today."),
        (4, "🟠 <b>Watch Closely (Gem 4)</b>", "No Gem 4 signals today."),
        (3, "🟡 <b>On the Radar (Gem 3)</b>", "No Gem 3 signals today."),
    ]

    for score, label, empty_msg in tier_defs:
        lines.append(label)
        if tiers[score]:
            for s in tiers[score]:
                emoji = _CAT_EMOJI.get(s.get("category", ""), "•")
                lines.append(f"{emoji} <b>{_esc(s.get('headline'))}</b>")
                lines.append(f"🇯🇵 {_esc(s.get('japan_angle'))}")
                if s.get("source_url"):
                    lines.append(f"🔗 {_esc(s.get('source_url'))}")
                lines.append("")
        else:
            lines.append(empty_msg)
        lines.append("")

    background = (tiers[2] + tiers[1])[:3]
    lines.append("⚪ <b>Background (Gem 1-2)</b>")
    if background:
        for s in background:
            emoji = _CAT_EMOJI.get(s.get("category", ""), "•")
            lines.append(f"{emoji} {_esc(s.get('headline'))}")
        lines.append("")
    else:
        lines.append("No Gem 1-2 signals today.")

    return "\n".join(lines).strip()


def _build_breaking_html(breaking_signals: list, run_date: str) -> str:
    lines = [f"🚨 <b>BREAKING — {_esc(run_date)}</b>", ""]
    for i, s in enumerate(breaking_signals[:3], 1):
        lines.append(f"{i}. <b>{_esc(s.get('headline'))}</b>")
        lines.append(f"🇯🇵 {_esc(s.get('japan_angle'))}")
        if s.get("source_url"):
            lines.append(f"🔗 {_esc(s.get('source_url'))}")
        lines.append("")
    return "\n".join(lines).strip()


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

def _search_serpapi(query: str, max_results: int = 10,
                    japanese_sources: bool = False,
                    news_only: bool = True,
                    time_limit: str | None = "qdr:d") -> list:
    api_key = os.environ.get("SEARCH_API_KEY", "")
    if not api_key:
        return [{"title": "SEARCH_API_KEY not configured", "snippet": "",
                 "url": "", "published_date": datetime.date.today().isoformat(),
                 "source_language": "en"}]
    params = {
        "q": query, "num": max_results, "api_key": api_key,
    }
    if news_only:
        params["tbm"] = "nws"
        params["sort"] = "date"
    if time_limit:
        params["tbs"] = time_limit
        
    if japanese_sources:
        params["gl"] = "jp"
        params["hl"] = "ja"
    try:
        resp = requests.get("https://serpapi.com/search", params=params, timeout=20)
        resp.raise_for_status()
        data = resp.json()
        
        results_key = "news_results" if news_only else "organic_results"
        raw_results = data.get(results_key, [])
        
        return [
            {
                "title": r.get("title", ""),
                "snippet": r.get("snippet", r.get("description", "")),
                "url": r.get("link", ""),
                "published_date": r.get("date", datetime.date.today().isoformat()),
                "source_language": "ja" if japanese_sources else "en",
            }
            for r in raw_results
        ]
    except Exception as e:
        print(f"[search] Error for '{query}': {e}")
        return []


def _format_articles_for_classifier(results: list) -> tuple[str, dict]:
    """Format articles as numbered text for classifier, return (text, url_lookup).

    Each article gets a unique [N] ID. url_lookup maps str(N) → real URL.
    The classifier outputs article_id=N; Python resolves to real URL.
    """
    url_lookup = {}
    lines = []
    idx = 0
    for r in results:
        url = r.get("url", "")
        title = r.get("title", "")
        snippet = r.get("snippet", "")
        lang = r.get("source_language", "en")
        lang_note = " [JA]" if lang == "ja" else ""

        url_lookup[str(idx)] = url
        lines.append(
            f"[{idx}]{lang_note} {title}\n"
            f"    SNIPPET: {snippet}"
        )
        idx += 1

    return "\n\n".join(lines), url_lookup


def _is_recent(published_date: str, hours: int = 24) -> bool:
    if not published_date:
        return True
    pd = published_date.lower()
    if any(x in pd for x in ["minute", "hour", "just now"]):
        return True
    if "day" in pd:
        try:
            n = int(pd.split()[0])
            return n * 24 <= hours
        except Exception:
            return True
    return True


def search_ai_news(query: str, max_results: int = 10,
                   japanese_sources: bool = False) -> str:
    """Search tool for on_demand_router. Returns JSON string of results."""
    # Since Q&A mode is not limited to 24-hour news, perform a general search
    results = _search_serpapi(query, max_results, japanese_sources, news_only=False, time_limit=None)
    return json.dumps(results)


def write_digest_to_memory(date_key: str, digest: str) -> str:
    validated = MemoryWriteInput(date_key=date_key, digest=digest)
    memory_dir = ".agents/memory"
    os.makedirs(memory_dir, exist_ok=True)
    path = os.path.join(memory_dir, f"{validated.date_key}.json")
    try:
        json.loads(validated.digest)
        with open(path, "w", encoding="utf-8") as f:
            f.write(validated.digest)
        return f"Stored digest for {validated.date_key}."
    except json.JSONDecodeError as e:
        return f"Error: not valid JSON — {e}"
    except OSError as e:
        return f"Error writing to memory: {e}"


def read_digests_from_memory(query: str, lookback_days: int = 7) -> str:
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
            with open(os.path.join(memory_dir, filename), "r", encoding="utf-8") as f:
                results.append(json.load(f))
        return json.dumps(results)
    except OSError as e:
        return json.dumps({"error": str(e)})


# ---------------------------------------------------------------------------
# Python nodes
# ---------------------------------------------------------------------------

@node
def detect_trigger(ctx: Context, node_input: Any):
    """Parse delivery_mode from Pub/Sub payload. Routes: scan or query."""
    raw = node_input
    if hasattr(raw, "parts"):
        raw = " ".join(p.text for p in (raw.parts or []) if hasattr(p, "text") and p.text)
    elif isinstance(raw, dict):
        parts = raw.get("parts", [])
        raw = " ".join(p.get("text", "") for p in parts if isinstance(p, dict)) if parts \
            else raw.get("text", str(node_input))

    text = str(raw).strip()

    try:
        payload = json.loads(text)
        if "data" in payload and isinstance(payload["data"], dict):
            payload = payload["data"]
        trigger_word = payload.get("trigger", "").lower()
        user_question = payload.get("question", "")
    except (json.JSONDecodeError, AttributeError):
        trigger_word = text.lower()
        user_question = text

    if trigger_word in ("digest", "", "scheduled", "run digest"):
        delivery_mode = "digest"
        route = "scan"
    elif trigger_word == "monitor":
        delivery_mode = "monitor"
        route = "scan"
    else:
        delivery_mode = "query"
        route = "query"
        if not user_question:
            user_question = text

    yield Event(
        output=raw,
        state={
            "delivery_mode": delivery_mode,
            "user_query": user_question or text,
            "run_date": datetime.date.today().isoformat(),
        },
        route=route,
    )


def _deduplicate_articles(batches: list[list[dict]], hours: int = 24) -> list[dict]:
    """Deduplicate similar articles across search batches using keyword overlap (bilingual)."""
    seen_urls = set()
    seen_titles = []
    deduped = []
    
    IGNORE_WORDS = {
        "japan", "japanese", "ai", "news", "policy", "government", "model",
        "article", "report", "company", "tech", "system", "industry", "market",
        "business", "introducing", "introduction", "introduce", "latest", "new"
    }

    def get_title_keywords(title: str) -> set[str]:
        t = title.lower()
        eng_words = set(re.findall(r'\b[a-z]{3,}\b', t))
        # Support Japanese kanji/katakana deduplication
        jp_words = set(re.findall(r'[\u4e00-\u9fff\u30a0-\u30ff]{2,}', t))
        return (eng_words.union(jp_words)) - IGNORE_WORDS

    for batch in batches:
        for r in batch:
            url = r.get("url", "")
            title = r.get("title", "").strip()
            if not url or not title:
                continue
            if url in seen_urls:
                continue
                
            # Deduplicate by title keyword similarity (>55% overlap treated as duplicate)
            title_words = get_title_keywords(title)
            is_dup = False
            for seen_words in seen_titles:
                if len(title_words) > 0 and len(seen_words) > 0:
                    overlap_ratio = len(title_words.intersection(seen_words)) / max(len(title_words), len(seen_words))
                    if overlap_ratio > 0.55:
                        is_dup = True
                        break
            if is_dup:
                continue
                
            seen_urls.add(url)
            seen_titles.append(title_words)
            if _is_recent(r.get("published_date", ""), hours=hours):
                deduped.append(r)
                
    return deduped


@node
def prepare_digest_queries(ctx: Context, node_input: Any):
    """Run 8 concurrent searches, deduplicate results, format with [N] IDs."""
    search_specs = [
        ("Japan AI policy METI government", False),
        ("AI 政策 経済産業省 日本", True),
        ("new AI model release Japan enterprise", False),
        ("AI モデル 発表 日本 企業", True),
        ("AI enterprise deployment Japan manufacturing", False),
        ("AI 企業 導入 日本 製造業", True),
        ("AI company Japan partnership SoftBank NTT Sakana", False),
        ("AI research product disruption agent", False),
    ]

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(_search_serpapi, q, 10, jp) for q, jp in search_specs]
        batches = []
        for f in concurrent.futures.as_completed(futures, timeout=30):
            try:
                batches.append(f.result())
            except Exception as e:
                print(f"[search] Batch error: {e}")
                batches.append([])

    all_results = _deduplicate_articles(batches, hours=24)

    en = sum(1 for r in all_results if r.get("source_language") == "en")
    ja = sum(1 for r in all_results if r.get("source_language") == "ja")
    print(f"[prepare_digest_queries] {len(all_results)} results ({ja} Japanese, {en} English)")

    formatted_text, url_lookup = _format_articles_for_classifier(all_results)

    yield Event(
        output=formatted_text,
        state={
            "raw_news": formatted_text,
            "raw_news_json": json.dumps(all_results, ensure_ascii=False),
            "url_lookup": json.dumps(url_lookup),
        },
    )


def _clean_query_for_search(query: str) -> str:
    """Strip conversational phrasing and question marks to get clean search keywords."""
    q = query.lower().strip()
    # Strip question marks and punctuation, but keep internal periods for domains/emails
    q = re.sub(r'[?!\,\:\;\"]', '', q)
    q = q.rstrip('.')
    prefixes = [
        "how about", "what about", "tell me about", "do you know about",
        "can you tell me about", "what is", "who is", "information on",
        "search for", "look up", "find news about"
    ]
    for p in prefixes:
        if q.startswith(p):
            q = q[len(p):].strip()
    return q or query


@node
def after_on_demand_router(ctx: Context, node_input: Any):
    """Run live search for the user's query, format with [N] IDs, store url_lookup."""
    user_query = ctx.state.get("user_query", str(node_input))
    routed = ctx.state.get("routed_query", "")

    # Python-level Data Leakage Prevention (DLP) guardrail before query runs
    PII_PATTERNS = [
        r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b",  # email
        r"\b\d{3}[-.]?\d{3}[-.]?\d{4}\b",                       # phone
    ]
    INJECTION_PATTERNS = [
        r"ignore\s+previous",
        r"ignore\s+(?:all\s+)?instructions?",
        r"system\s+prompt",
        r"jailbreak",
        r"disregard\s+instructions?",
        r"act\s+as\s+if",
        r"pretend\s+you",
        r"<script",
        r"DROP\s+TABLE",
        r"rm\s+-rf",
    ]
    
    # Block immediately if query violates safety patterns
    for pattern in PII_PATTERNS:
        if re.search(pattern, user_query, re.IGNORECASE):
            print(f"[safety] BLOCKED: PII detected in user query: {user_query}")
            yield Event(
                output="Blocked: PII detected in query.",
                state={
                    "raw_news": "Blocked: PII detected in query.",
                    "raw_news_json": "[]",
                    "url_lookup": "{}",
                },
                route="to_classifier"
            )
            return

    for pattern in INJECTION_PATTERNS:
        if re.search(pattern, user_query, re.IGNORECASE):
            print(f"[safety] BLOCKED: Injection detected in user query: {user_query}")
            yield Event(
                output="Blocked: Prompt injection detected.",
                state={
                    "raw_news": "Blocked: Prompt injection detected.",
                    "raw_news_json": "[]",
                    "url_lookup": "{}",
                },
                route="to_classifier"
            )
            return

    cleaned_query = _clean_query_for_search(user_query)
    print(f"[on_demand] Searching live for: {cleaned_query}")
    # Perform general web search with no time limit for Q&A
    live_results = _search_serpapi(cleaned_query, max_results=10, japanese_sources=False, news_only=False, time_limit=None)

    formatted_text, url_lookup = _format_articles_for_classifier(live_results)

    # Include memory context as plain text (not numbered — no URL to attach)
    combined = formatted_text
    if routed:
        combined = f"MEMORY CONTEXT (no URLs):\n{routed}\n\nLIVE SEARCH RESULTS:\n{formatted_text}"

    yield Event(
        output=combined,
        state={
            "raw_news": combined,
            "raw_news_json": json.dumps(live_results, ensure_ascii=False),
            "url_lookup": json.dumps(url_lookup),
        },
        route="to_classifier",
    )


@node
def route_by_gem_score(ctx: Context, node_input: Any):
    """Resolve article_id → real URL for all paths. Route by delivery_mode."""
    classified = ctx.state.get("classified_signals", {})
    signals_list = _extract_signals(classified)
    print(f"[route_by_gem_score] received {len(signals_list)} signals from classifier")

    # Load url_lookup built by prepare_digest_queries or after_on_demand_router
    url_lookup: dict = {}
    try:
        url_lookup = json.loads(ctx.state.get("url_lookup", "{}"))
    except Exception:
        pass

    import re

    # Load raw news articles to do keyword-based self-healing URL matching
    articles = []
    try:
        articles = json.loads(ctx.state.get("raw_news_json", "[]"))
    except Exception:
        pass

    resolved_signals = []
    verified = 0
    for s in signals_list:
        if not isinstance(s, dict):
            continue
        
        raw_id = str(s.get("article_id", "-1")).strip()
        match = re.search(r'\d+', raw_id)
        suggested_idx = int(match.group(0)) if match else -1

        # Self-healing keyword matching
        headline = s.get("headline", "")
        # Find proper nouns (capitalized words except the first word of the headline)
        original_words = re.findall(r'\b[A-Za-z0-9\.\-]+\b', headline)
        proper_nouns = set()
        for idx, w in enumerate(original_words):
            if idx > 0 and w[0].isupper():
                proper_nouns.add(w.lower())
        
        # Numbers are also treated as highly specific keywords
        numbers = set(re.findall(r'\b\d+\b', headline))
        high_weight_words = proper_nouns.union(numbers)

        headline_words = set(re.findall(r'\b[a-z]{3,}\b', headline.lower()))
        
        # Exclude generic keywords that appear in almost all articles to prevent false-positive matches
        IGNORE_WORDS = {
            "japan", "japanese", "ai", "news", "policy", "government", "model",
            "article", "report", "company", "tech", "system", "industry", "market",
            "business", "introducing", "introduction", "introduce", "latest", "new"
        }
        specific_headline_words = headline_words - IGNORE_WORDS
        high_weight_words = high_weight_words - IGNORE_WORDS

        # Cross-lingual synonyms for common Japanese tech/gov terms to assist matching
        JAPAN_SYNONYMS = {
            "防衛": ["defense", "defence", "forces", "military", "sdf", "jsdf", "palantir"],
            "自衛": ["defense", "defence", "forces", "military", "sdf", "jsdf"],
            "経済産業省": ["meti", "ministry", "policy"],
            "経産省": ["meti", "ministry", "policy"],
            "政府": ["government", "policy"],
            "導入": ["adopt", "adoption", "introduce", "introducing", "deployment"],
            "開発": ["develop", "development", "build"],
            "発表": ["announce", "announcement", "release"],
            "提携": ["partner", "partnership", "alliance"],
        }

        def calculate_score(art: dict) -> int:
            title_snippet = (art.get("title", "") + " " + art.get("snippet", "")).lower()
            art_words = set(re.findall(r'\b[a-z]{3,}\b', title_snippet))
            
            # 1. Base specific overlap (weight=1)
            score = len(specific_headline_words.intersection(art_words))
            
            # 2. Proper nouns / numbers overlap (weight=5)
            high_weight_overlap = high_weight_words.intersection(art_words)
            score += len(high_weight_overlap) * 5
            
            # 3. Cross-lingual synonym match (weight=3)
            for jp_term, eng_syns in JAPAN_SYNONYMS.items():
                if jp_term in title_snippet:
                    if any(eng in specific_headline_words for eng in eng_syns):
                        score += 3
            return score

        # Calculate scores for all articles first
        scores = [calculate_score(art) for art in articles]
        max_score = max(scores) if scores else 0
        best_idx = scores.index(max_score) if max_score > 0 else -1
        
        real_url = ""
        # 1. Try suggested index first if it's within range
        if 0 <= suggested_idx < len(articles):
            suggested_score = scores[suggested_idx]
            # Trust the suggested ID only if its score is close (within 3 points) to the maximum score
            if suggested_score > 0 and (max_score - suggested_score) <= 3:
                real_url = articles[suggested_idx].get("url", "")
                print(f"[route] Trusting LLM ID {suggested_idx} (score={suggested_score}, max={max_score})")

        # 2. If suggested ID was wrong, missing, or had a significantly worse score, self-heal to best match
        if not real_url and best_idx != -1:
            suggested_score = scores[suggested_idx] if 0 <= suggested_idx < len(articles) else 0
            real_url = articles[best_idx].get("url", "")
            print(f"[route] Self-healed ID {raw_id} -> {best_idx} (score={max_score}, suggested_score={suggested_score}, headline={headline[:40]!r})")
        elif not real_url and 0 <= suggested_idx < len(articles):
            # Fallback
            real_url = articles[suggested_idx].get("url", "")
            print(f"[route] Fallback to suggested ID {suggested_idx}")

        signal = {k: v for k, v in s.items() if k != "article_id"}
        signal["source_url"] = real_url
        resolved_signals.append(signal)
        if real_url:
            verified += 1

    print(f"[route_by_gem_score] {verified}/{len(resolved_signals)} signals have verified URLs")

    breaking_signals = [
        s for s in resolved_signals
        if s.get("breaking", False) is True and s.get("gem_score", 0) == 5
    ]

    delivery_mode = ctx.state.get("delivery_mode", "digest")

    if delivery_mode == "monitor" and breaking_signals:
        run_date = ctx.state.get("run_date", datetime.date.today().isoformat())
        _telegram_post(_build_breaking_html(breaking_signals, run_date), label="breaking alert")

    if hasattr(classified, "model_dump"):
        classified_dict = classified.model_dump()
    elif isinstance(classified, dict):
        classified_dict = classified
    else:
        classified_dict = {}

    classified_updated = {**classified_dict, "signals": resolved_signals}

    yield Event(
        output=node_input,
        state={
            "classified_signals": classified_updated,
            "breaking_signals": breaking_signals,
        },
        route=delivery_mode,
    )


@node
def monitor_finish(ctx: Context, node_input: Any):
    """Monitor terminal node. No LLM. Console status only."""
    breaking_signals = ctx.state.get("breaking_signals", [])
    run_date = ctx.state.get("run_date", datetime.date.today().isoformat())

    classified = ctx.state.get("classified_signals", {})
    signals = _extract_signals(classified)
    write_digest_to_memory(
        date_key=run_date,
        digest=json.dumps({"run_date": run_date, "delivery_mode": "monitor",
                           "signals": signals}, ensure_ascii=False),
    )

    if breaking_signals:
        headlines = ", ".join(s.get("headline", "")[:60] for s in breaking_signals[:3])
        console_msg = f"⚡ Breaking signal found: {headlines}"
    else:
        console_msg = "✅ Nothing important in the last 2 hours. Next scan coming."

    print(f"[monitor] {console_msg}")
    yield Event(output=console_msg, state={"stored": True})


@node
def store_and_finish(ctx: Context, node_input: Any):
    """Store signals and deliver digest or Q&A answer."""
    delivery_mode = ctx.state.get("delivery_mode", "digest")
    run_date = ctx.state.get("run_date", datetime.date.today().isoformat())
    classified = ctx.state.get("classified_signals", {})
    signals = _extract_signals(classified)

    write_digest_to_memory(
        date_key=run_date,
        digest=json.dumps({"run_date": run_date, "delivery_mode": delivery_mode,
                           "signals": signals}, ensure_ascii=False),
    )

    if delivery_mode == "digest":
        executive_summary = ctx.state.get("executive_summary", "")
        digest_html = _build_digest_html(signals, run_date, executive_summary)
        print("\n" + digest_html)
        _telegram_post(digest_html, label="daily digest")
        yield Event(output=digest_html, state={"stored": True})

    elif delivery_mode == "query":
        query_answer = ctx.state.get("query_answer", "")
        if not query_answer or "no recent signals" in query_answer.lower():
            query_answer = "No recent signals found for your query."
        print(f"\n[Q&A] {query_answer}")
        _telegram_post(query_answer, label="Q&A reply")
        yield Event(output=query_answer, state={"stored": True})


# ---------------------------------------------------------------------------
# LLM nodes
# ---------------------------------------------------------------------------

classifier = LlmAgent(
    name="classifier",
    model="gemini-2.5-flash",
    output_key="classified_signals",
    output_schema=DigestSignals,
    instruction=f"""You are a signal classifier for a PM AI Signal Tracker.

TODAY'S DATE: {datetime.date.today().isoformat()}

Read the news articles in ctx.state['raw_news']. Each article is formatted as:
  [N] Article title
      SNIPPET: snippet text

For each article that is relevant to a PM working on AI products in Japan:
1. Output article_id: the N from [N] at the start of that article
2. Copy the article title as the headline (translate Japanese [JA] titles to English)
3. Add your analysis: japan_angle, so_what, strategic_signal
4. Assign category and gem_score

Select each relevant article once. Do not combine multiple articles into one signal.
Do not invent headlines — use the actual article title.

SIGNAL CATEGORIES:
1. policy_sovereignty — METI directives, AI laws, government strategy
2. model_capability_release — model launches from Japan-committed companies
3. infrastructure_compute — DC builds, chip supply, cloud capacity in Japan
4. enterprise_adoption — Japan deployments + global use cases as leading indicators
5. competitive_moves — M&A, partnerships, Japan entity formation
6. research_disruptor_radar — papers with concrete product implication

GEM SCORING — use the FULL scale, most articles score 1-2:
5 — Immediate Japan action required THIS WEEK. Max 2 per digest.
4 — Strong Japan relevance, concrete action in 3-6 months. Max 3 per digest.
3 — Indirect Japan relevance, worth tracking. Most news lands here.
2 — Globally interesting but low Japan near-term impact. Very common.
1 — Noise: no product implication, no Japan relevance. Very common.

BREAKING: true only if gem_score=5 AND published last 2 hours AND market-shifting.

JAPAN-COMMITTED COMPANIES (releases from these are gems):
OpenAI Japan, Anthropic Japan, Google Japan, Microsoft Japan, AWS Japan,
NTT, Fujitsu, SoftBank, Sony, Sakana AI, Preferred Networks, NEC, Hitachi,
Toyota, Rakuten, NTT DATA, DeNA

HARD RULES:
- Translate [JA] article titles to English in the headline field.
- article_id must be the exact N from that article's [N] prefix.
- Max 15 signals total.
- Never score 4-5 without a concrete Japan implication.
- Output gem 1-2 signals for background noise — do not skip them.
""",
)


digest_formatter = LlmAgent(
    name="digest_formatter",
    model="gemini-2.5-flash",
    output_key="executive_summary",
    instruction=f"""You are the executive summary writer for PM AI Signal Tracker.

TODAY'S DATE: {datetime.date.today().isoformat()}

Write a 2-3 sentence executive summary of today's AI signals from a Japan PM
perspective. Focus on gem 4-5 signals. Reference specific companies and facts.
Output ONLY the summary text. Max 60 words.
""",
)


query_formatter = LlmAgent(
    name="query_formatter",
    model="gemini-2.5-flash",
    output_key="query_answer",
    tools=[read_digests_from_memory],
    instruction=f"""You are the Q&A responder for PM AI Signal Tracker.

TODAY'S DATE: {datetime.date.today().isoformat()}

The user's question is in ctx.state['user_query'].
Classified signals are in ctx.state['classified_signals'].

If classified_signals is empty, call read_digests_from_memory.
Only surface signals directly relevant to the question.
If nothing relevant found, output: "No recent signals found for your query."

OUTPUT FORMAT (short — goes to Telegram):
Start with a natural lead-in like "The most relevant signal on [topic]:"
then 2-3 sentences: key fact + Japan angle.
Add 🔗 [url] only if source_url is a real URL starting with http. Otherwise omit.

HARD RULES:
- Max 100 words. No repetition. No gem tier listing.
- Never surface unrelated signals as fallback.
- English only.
""",
)


on_demand_router = LlmAgent(
    name="on_demand_router",
    model="gemini-2.5-flash",
    output_key="routed_query",
    tools=[read_digests_from_memory, search_ai_news],
    instruction="""You are a retrieval tool for PM AI Signal Tracker.

NEVER ask the user questions. Just retrieve.

The user's question is in ctx.state['user_query']. Always:
1. Call read_digests_from_memory to check past signals
2. Call search_ai_news with the most relevant query

Write a brief summary of what you found. That is all.
""",
)


# ---------------------------------------------------------------------------
# Workflow
# ---------------------------------------------------------------------------

root_workflow = Workflow(
    name="pm_ai_signal_tracker",
    edges=[
        ("START", detect_trigger),

        (detect_trigger, {
            "scan": prepare_digest_queries,
            "query": on_demand_router,
        }),

        # Scheduled path: searches → classifier → route
        (prepare_digest_queries, classifier),

        # Query path: router → live search → classifier → route
        (on_demand_router, after_on_demand_router),
        (after_on_demand_router, {"to_classifier": classifier}),

        # Both paths merge at classifier → route_by_gem_score
        (classifier, route_by_gem_score),

        # Three-way split by delivery_mode
        (route_by_gem_score, {
            "digest": digest_formatter,
            "monitor": monitor_finish,
            "query": query_formatter,
        }),

        (digest_formatter, store_and_finish),
        (query_formatter, store_and_finish),
    ],
)

app = App(name="app", root_agent=root_workflow)