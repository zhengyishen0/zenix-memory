#!/usr/bin/env python3
"""
Real API cache test with OAuth token.

Usage: ANTHROPIC_TOKEN=$(claude setup-token) python test_cache_real.py <yaml_path>
"""

import json
import os
import sys
from pathlib import Path

import yaml
import requests

TOKEN = os.environ.get("ANTHROPIC_TOKEN", "")


def load_yaml_messages(yaml_path):
    """Load messages from YAML."""
    with open(yaml_path) as f:
        doc = yaml.safe_load(f)

    messages = []
    for msg in doc.get("messages", []):
        role = msg["role"]
        content = msg["content"]

        if isinstance(content, str):
            api_content = content
        else:
            api_content = []
            for block in content:
                if block["type"] == "text":
                    api_content.append({"type": "text", "text": block["text"]})
                elif block["type"] == "thinking":
                    thinking = {"type": "thinking", "thinking": block["text"]}
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


def test_cache(yaml_path, max_messages=10):
    """Test cache by sending messages to API."""
    if not TOKEN:
        print("Error: ANTHROPIC_TOKEN not set")
        print("Run: ANTHROPIC_TOKEN=$(claude setup-token) python test_cache_real.py <yaml>")
        return

    print(f"Loading YAML: {yaml_path}")
    messages = load_yaml_messages(Path(yaml_path))

    # Take first N messages
    test_messages = messages[:max_messages]

    # Add continuation message
    test_messages.append({
        "role": "user",
        "content": "Testing cache. Reply OK."
    })

    print(f"Sending {len(test_messages)} messages...")

    response = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "anthropic-beta": "oauth-2025-04-20",
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        },
        json={
            "model": "claude-sonnet-4-20250514",
            "max_tokens": 50,
            "messages": test_messages,
        }
    )

    print(f"\nStatus: {response.status_code}")

    if response.ok:
        data = response.json()
        print(f"Response: {data.get('content', [{}])[0].get('text', '')[:100]}")
        print(f"\nUsage:")
        usage = data.get('usage', {})
        print(f"  input_tokens: {usage.get('input_tokens', 0)}")
        print(f"  cache_creation_input_tokens: {usage.get('cache_creation_input_tokens', 0)}")
        print(f"  cache_read_input_tokens: {usage.get('cache_read_input_tokens', 0)}")

        if usage.get('cache_read_input_tokens', 0) > 0:
            print("\n✓ CACHE HIT! The YAML format is cache-compatible.")
        else:
            print("\n⚠ No cache hit (first request creates cache, run again to verify)")
    else:
        print(f"Error: {response.text}")


if __name__ == "__main__":
    yaml_path = sys.argv[1] if len(sys.argv) > 1 else "/tmp/test_session.yaml"
    max_msgs = int(sys.argv[2]) if len(sys.argv) > 2 else 10
    test_cache(yaml_path, max_msgs)
