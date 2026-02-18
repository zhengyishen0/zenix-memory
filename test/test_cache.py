#!/usr/bin/env python3
"""
Test KV cache compatibility by:
1. Loading a YAML session
2. Sending to Anthropic API with "hi, resuming"
3. Checking cache_read_input_tokens in response
"""

import json
import os
import sys
from pathlib import Path

try:
    import yaml
    import anthropic
except ImportError:
    print("pip install pyyaml anthropic")
    sys.exit(1)


def yaml_to_api_messages(yaml_path: Path) -> list:
    """Convert YAML to API messages format."""
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
                    api_content.append({
                        "type": "tool_result",
                        "tool_use_id": block["tool_use_id"],
                        "content": block.get("content", "")
                    })

            # If empty after filtering, use empty string
            if not api_content:
                continue

        messages.append({"role": role, "content": api_content})

    return messages


def test_cache(yaml_path: str, max_messages: int = 10):
    """Test cache by sending messages to API."""

    client = anthropic.Anthropic()

    # Load and convert YAML
    messages = yaml_to_api_messages(Path(yaml_path))

    # Take first N messages for testing (to limit cost)
    test_messages = messages[:max_messages]

    # Add a new message to continue
    test_messages.append({
        "role": "user",
        "content": "Hi, just testing if this conversation resumes correctly. Reply with just 'OK'."
    })

    print(f"Testing with {len(test_messages)} messages...")
    print(f"Messages: {[m['role'] for m in test_messages]}")

    # Send to API
    try:
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=100,
            messages=test_messages
        )

        print(f"\nResponse: {response.content[0].text[:200]}")
        print(f"\nUsage:")
        print(f"  input_tokens: {response.usage.input_tokens}")
        print(f"  output_tokens: {response.usage.output_tokens}")

        # Check for cache metrics
        if hasattr(response.usage, 'cache_creation_input_tokens'):
            print(f"  cache_creation_input_tokens: {response.usage.cache_creation_input_tokens}")
        if hasattr(response.usage, 'cache_read_input_tokens'):
            print(f"  cache_read_input_tokens: {response.usage.cache_read_input_tokens}")

    except anthropic.BadRequestError as e:
        print(f"API Error: {e}")
        print("\nThis might be due to:")
        print("- Invalid thinking block signatures")
        print("- Tool use/result mismatch")
        print("- Message ordering issues")


def test_original_jsonl(session_id: str, max_messages: int = 10):
    """Test with original JSONL for comparison."""
    from convert import find_jsonl, parse_jsonl

    client = anthropic.Anthropic()

    jsonl_path = find_jsonl(session_id)

    # Parse and build messages directly from JSONL
    messages = []
    with open(jsonl_path) as f:
        for line in f:
            try:
                rec = json.loads(line)
                if rec.get("type") in ("user", "assistant"):
                    msg = rec.get("message", {})
                    if msg.get("role") and msg.get("content"):
                        # Skip thinking blocks (no signature)
                        content = msg["content"]
                        if isinstance(content, list):
                            content = [b for b in content if b.get("type") != "thinking"]
                            if not content:
                                continue
                        messages.append({
                            "role": msg["role"],
                            "content": content
                        })
            except:
                continue

    test_messages = messages[:max_messages]
    test_messages.append({
        "role": "user",
        "content": "Hi, testing original JSONL. Reply 'OK'."
    })

    print(f"\nTesting ORIGINAL JSONL with {len(test_messages)} messages...")

    try:
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=100,
            messages=test_messages
        )

        print(f"Response: {response.content[0].text[:200]}")
        print(f"\nUsage:")
        print(f"  input_tokens: {response.usage.input_tokens}")
        if hasattr(response.usage, 'cache_read_input_tokens'):
            print(f"  cache_read_input_tokens: {response.usage.cache_read_input_tokens}")

    except anthropic.BadRequestError as e:
        print(f"API Error: {e}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: test_cache.py <yaml_file> [max_messages]")
        print("       test_cache.py --jsonl <session_id> [max_messages]")
        sys.exit(1)

    if sys.argv[1] == "--jsonl":
        session_id = sys.argv[2]
        max_msgs = int(sys.argv[3]) if len(sys.argv) > 3 else 10
        test_original_jsonl(session_id, max_msgs)
    else:
        yaml_path = sys.argv[1]
        max_msgs = int(sys.argv[2]) if len(sys.argv) > 2 else 10
        test_cache(yaml_path, max_msgs)
