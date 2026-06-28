"""
validate_search.py
Pre-tool hook that runs before every search_ai_news call.
Reads tool args from stdin, blocks unsafe queries.
exit(0) = APPROVED, exit(1) = BLOCKED
"""
import json
import re
import sys

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

PII_PATTERNS = [
    r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b",  # email
    r"\b\d{3}[-.]?\d{3}[-.]?\d{4}\b",               # phone
    r"\b\d{4}[- ]?\d{4}[- ]?\d{4}[- ]?\d{4}\b",    # credit card
]

try:
    tool_args = json.loads(sys.stdin.read())
    query = tool_args.get("query", "")

    for pattern in INJECTION_PATTERNS:
        if re.search(pattern, query, re.IGNORECASE):
            print(f"BLOCKED: injection pattern detected in query: '{query}'")
            sys.exit(1)

    for pattern in PII_PATTERNS:
        if re.search(pattern, query, re.IGNORECASE):
            print(f"BLOCKED: PII pattern detected in query.")
            sys.exit(1)

    if len(query) > 200:
        print(f"BLOCKED: query exceeds 200 character limit.")
        sys.exit(1)

    print(f"APPROVED: query '{query[:80]}...' passed validation.")
    sys.exit(0)

except Exception as e:
    print(f"Hook error: {e}")
    sys.exit(1)
