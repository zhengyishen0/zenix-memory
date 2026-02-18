#!/usr/bin/env python3
"""
Compare JSONL vs YAML message formats to verify they're identical for cache.

This doesn't call the API - it verifies the data structures match exactly.
If they match, cache should work.
"""

import json
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("pip install pyyaml")
    sys.exit(1)


def load_jsonl_messages(jsonl_path: Path) -> list:
    """Load messages from JSONL (what Claude Code sends to API)."""
    messages = []
    with open(jsonl_path) as f:
        for line in f:
            try:
                rec = json.loads(line)
                if rec.get("type") in ("user", "assistant"):
                    msg = rec.get("message", {})
                    if msg.get("role") and msg.get("content") is not None:
                        messages.append({
                            "role": msg["role"],
                            "content": msg["content"]
                        })
            except json.JSONDecodeError:
                continue
    return messages


def load_yaml_messages(yaml_path: Path) -> list:
    """Load messages from YAML and convert to API format."""
    with open(yaml_path) as f:
        doc = yaml.safe_load(f)

    messages = []
    for msg in doc.get("messages", []):
        role = msg["role"]
        content = msg["content"]

        # Convert to API format
        if isinstance(content, str):
            api_content = content
        else:
            api_content = []
            for block in content:
                if block["type"] == "text":
                    api_content.append({"type": "text", "text": block["text"]})
                elif block["type"] == "thinking":
                    thinking = {
                        "type": "thinking",
                        "thinking": block["text"],
                    }
                    if "signature" in block:
                        thinking["signature"] = block["signature"]
                    api_content.append(thinking)
                elif block["type"] == "tool_use":
                    api_content.append({
                        "type": "tool_use",
                        "id": block["id"],
                        "name": block["name"],
                        "input": block["input"]
                    })
                elif block["type"] == "tool_result":
                    result = {
                        "type": "tool_result",
                        "tool_use_id": block["tool_use_id"],
                        "content": block.get("content", "")
                    }
                    if "is_error" in block:
                        result["is_error"] = block["is_error"]
                    api_content.append(result)

        messages.append({"role": role, "content": api_content})

    return messages


def normalize_content(content):
    """Normalize content for comparison."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        normalized = []
        for block in content:
            if isinstance(block, dict):
                # Sort keys for consistent comparison
                b = {k: v for k, v in sorted(block.items())}
                normalized.append(b)
            else:
                normalized.append(block)
        return normalized
    return content


def compare_messages(jsonl_msgs: list, yaml_msgs: list) -> tuple:
    """Compare messages and return (match_count, diff_count, diffs)."""
    matches = 0
    diffs = []

    max_len = max(len(jsonl_msgs), len(yaml_msgs))

    for i in range(max_len):
        j_msg = jsonl_msgs[i] if i < len(jsonl_msgs) else None
        y_msg = yaml_msgs[i] if i < len(yaml_msgs) else None

        if j_msg is None:
            diffs.append((i, "YAML has extra message", y_msg))
            continue
        if y_msg is None:
            diffs.append((i, "JSONL has extra message", j_msg))
            continue

        # Compare roles
        if j_msg["role"] != y_msg["role"]:
            diffs.append((i, f"Role mismatch: {j_msg['role']} vs {y_msg['role']}", None))
            continue

        # Compare content (normalized)
        j_content = normalize_content(j_msg["content"])
        y_content = normalize_content(y_msg["content"])

        if j_content != y_content:
            # Check if it's just a type difference (str vs list)
            if isinstance(j_content, str) and isinstance(y_content, list):
                if len(y_content) == 1 and y_content[0].get("type") == "text":
                    if j_content == y_content[0].get("text"):
                        matches += 1
                        continue

            diffs.append((i, "Content mismatch", {
                "jsonl": str(j_content)[:200],
                "yaml": str(y_content)[:200]
            }))
        else:
            matches += 1

    return matches, len(diffs), diffs


def find_jsonl(session_id: str) -> Path:
    """Find JSONL file by session ID."""
    claude_projects = Path.home() / ".claude" / "projects"
    for project_dir in claude_projects.iterdir():
        if not project_dir.is_dir():
            continue
        for jsonl in project_dir.glob("*.jsonl"):
            if session_id in jsonl.stem:
                return jsonl
    raise FileNotFoundError(f"Session not found: {session_id}")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: test_cache_compare.py <session_id> <yaml_file>")
        print("\nCompares original JSONL messages with converted YAML messages.")
        print("If they match exactly (except thinking signatures), cache should work.")
        sys.exit(1)

    session_id = sys.argv[1]
    yaml_path = Path(sys.argv[2])

    print(f"Loading JSONL for session: {session_id}")
    jsonl_path = find_jsonl(session_id)
    jsonl_msgs = load_jsonl_messages(jsonl_path)
    print(f"  Found {len(jsonl_msgs)} messages")

    print(f"\nLoading YAML: {yaml_path}")
    yaml_msgs = load_yaml_messages(yaml_path)
    print(f"  Found {len(yaml_msgs)} messages")

    print("\nComparing messages...")
    matches, diff_count, diffs = compare_messages(jsonl_msgs, yaml_msgs)

    print(f"\nResults:")
    print(f"  Matches: {matches}")
    print(f"  Differences: {diff_count}")

    if diffs:
        print(f"\nFirst 5 differences:")
        for i, (idx, reason, detail) in enumerate(diffs[:5]):
            print(f"  [{idx}] {reason}")
            if detail:
                print(f"       {detail}")

    if diff_count == 0:
        print("\n✓ YAML is cache-compatible with JSONL!")
        print("  (except thinking signatures which can't be preserved)")
    else:
        print(f"\n✗ Found {diff_count} differences. Cache may not work.")
