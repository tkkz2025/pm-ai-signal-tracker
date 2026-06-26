"""
validate_memory_write.py
Pre-tool hook that runs before every write_digest_to_memory call.
Validates date_key format and that digest is valid JSON.
exit(0) = APPROVED, exit(1) = BLOCKED
"""
import json
import re
import sys

DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")

try:
    tool_args = json.loads(sys.stdin.read())
    date_key = tool_args.get("date_key", "")
    digest = tool_args.get("digest", "")

    if not DATE_PATTERN.match(date_key):
        print(f"BLOCKED: date_key '{date_key}' is not a valid ISO date (YYYY-MM-DD).")
        sys.exit(1)

    try:
        json.loads(digest)
    except json.JSONDecodeError as e:
        print(f"BLOCKED: digest is not valid JSON: {e}")
        sys.exit(1)

    if len(digest) > 100_000:
        print("BLOCKED: digest exceeds 100KB size limit.")
        sys.exit(1)

    print(f"APPROVED: memory write for {date_key} passed validation.")
    sys.exit(0)

except Exception as e:
    print(f"Hook error: {e}")
    sys.exit(1)
