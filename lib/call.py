#!/usr/bin/env python3
"""
Direct API call using YAML session context.

Usage:
    call.py <yaml_file> <model_id> <endpoint> "prompt"

    # With OAuth token from stdin
    echo "$TOKEN" | call.py session.yaml claude-haiku-4-5 https://api.anthropic.com/v1/messages "question"
"""

import json
import os
import sys
from pathlib import Path

try:
    import yaml
    import requests
except ImportError:
    print("pip install pyyaml requests", file=sys.stderr)
    sys.exit(1)


def yaml_to_api_messages(yaml_path: Path) -> list:
    """Convert YAML to API messages format."""
    with open(yaml_path) as f:
        doc = yaml.safe_load(f)

    if not doc:
        return []

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


def call_api(endpoint: str, model: str, token: str, messages: list, prompt: str) -> str:
    """Call Anthropic API and return response text."""
    # Append user prompt
    messages.append({"role": "user", "content": prompt})

    # Determine auth header
    if token.startswith("sk-ant-oat"):
        # OAuth token
        headers = {
            "Authorization": f"Bearer {token}",
            "anthropic-beta": "oauth-2025-04-20",
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }
    else:
        # API key
        headers = {
            "x-api-key": token,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }

    response = requests.post(
        endpoint,
        headers=headers,
        json={
            "model": model,
            "max_tokens": 4096,
            "messages": messages,
        }
    )

    if not response.ok:
        print(f"API Error: {response.status_code}", file=sys.stderr)
        print(response.text, file=sys.stderr)
        sys.exit(1)

    data = response.json()

    # Extract text from response
    content = data.get("content", [])
    text_parts = []
    for block in content:
        if block.get("type") == "text":
            text_parts.append(block.get("text", ""))

    return "\n".join(text_parts)


def main():
    if len(sys.argv) < 5:
        print(__doc__, file=sys.stderr)
        sys.exit(1)

    yaml_path = Path(sys.argv[1])
    model = sys.argv[2]
    endpoint = sys.argv[3]
    prompt = sys.argv[4]

    # Get token from env or stdin
    token = os.environ.get("ANTHROPIC_TOKEN", "")
    if not token and not sys.stdin.isatty():
        token = sys.stdin.read().strip()

    if not token:
        print("Error: ANTHROPIC_TOKEN not set", file=sys.stderr)
        print("Run: export ANTHROPIC_TOKEN=$(claude setup-token)", file=sys.stderr)
        sys.exit(1)

    # Load messages from YAML
    if yaml_path.exists():
        messages = yaml_to_api_messages(yaml_path)
    else:
        messages = []

    # Call API
    response = call_api(endpoint, model, token, messages, prompt)
    print(response)


if __name__ == "__main__":
    main()
