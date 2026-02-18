#!/usr/bin/env python3
"""
Bidirectional converter: Claude Code JSONL <-> YAML unified format

Usage:
    convert.py jsonl2yaml <session-id>   # Convert JSONL to YAML
    convert.py yaml2jsonl <yaml-file>    # Convert YAML back to JSONL
    convert.py test <session-id>         # Round-trip test
"""

import json
import sys
import os
from pathlib import Path
from datetime import datetime
import re

try:
    import yaml
except ImportError:
    print("pip install pyyaml")
    sys.exit(1)


def find_jsonl(session_id: str) -> Path:
    """Find JSONL file by session ID (full or partial)."""
    claude_projects = Path.home() / ".claude" / "projects"
    for project_dir in claude_projects.iterdir():
        if not project_dir.is_dir():
            continue
        for jsonl in project_dir.glob("*.jsonl"):
            if session_id in jsonl.stem:
                return jsonl
    raise FileNotFoundError(f"Session not found: {session_id}")


def parse_jsonl(jsonl_path: Path) -> dict:
    """Parse Claude Code JSONL into structured data."""
    records = {"user": [], "assistant": [], "system": [], "summary": []}

    with open(jsonl_path) as f:
        for line in f:
            try:
                record = json.loads(line.strip())
                rec_type = record.get("type")
                if rec_type in records:
                    records[rec_type].append(record)
            except json.JSONDecodeError:
                continue

    return records


def extract_metadata(records: dict, jsonl_path: Path) -> dict:
    """Extract metadata from system records."""
    meta = {
        "id": jsonl_path.stem,
        "source": "claude-code",
        "created": None,
        "project": None,
        "branch": None,
    }

    # Get from first system record
    if records["system"]:
        first_sys = records["system"][0]
        meta["project"] = first_sys.get("cwd", "")
        meta["branch"] = first_sys.get("gitBranch", "")
        if "timestamp" in first_sys:
            meta["created"] = first_sys["timestamp"]

    # Get summary from latest
    if records["summary"]:
        meta["summary"] = records["summary"][-1].get("summary", "")
    else:
        meta["summary"] = ""

    meta["tags"] = []

    return meta


def convert_messages(records: dict) -> list:
    """Convert user/assistant records to unified message format."""
    messages = []

    # Combine and sort by timestamp/order
    all_msgs = []

    for rec in records["user"]:
        msg = rec.get("message", {})
        all_msgs.append({
            "type": "user",
            "record": rec,
            "message": msg,
            "uuid": rec.get("uuid", ""),
        })

    for rec in records["assistant"]:
        msg = rec.get("message", {})
        all_msgs.append({
            "type": "assistant",
            "record": rec,
            "message": msg,
            "uuid": rec.get("uuid", ""),
        })

    # Sort by uuid or timestamp (uuid contains ordering in Claude Code)
    # Actually, we'll preserve file order by using enumerate
    all_msgs_with_order = []

    with open(find_jsonl(records.get("_session_id", ""))) as f:
        order = 0
        for line in f:
            try:
                rec = json.loads(line)
                if rec.get("type") in ("user", "assistant"):
                    all_msgs_with_order.append((order, rec))
                    order += 1
            except:
                continue

    # Convert each message
    for order, rec in all_msgs_with_order:
        msg = rec.get("message", {})
        role = msg.get("role", rec.get("type"))

        unified = {
            "role": role,
        }

        # Add timestamp if available
        ts = rec.get("timestamp")
        if ts:
            unified["ts"] = ts

        # Process content
        content = msg.get("content")
        if isinstance(content, str):
            unified["content"] = content
        elif isinstance(content, list):
            # Complex content (tool_use, tool_result, thinking, text)
            unified["content"] = process_content_blocks(content)

        messages.append(unified)

    return messages


def process_content_blocks(blocks: list):
    """Process content blocks, simplifying where possible."""
    processed = []

    for block in blocks:
        block_type = block.get("type")

        if block_type == "text":
            processed.append({
                "type": "text",
                "text": block.get("text", "")
            })

        elif block_type == "thinking":
            thinking_block = {
                "type": "thinking",
                "text": block.get("thinking", "")
            }
            # Preserve signature for API cache compatibility
            if "signature" in block:
                thinking_block["signature"] = block["signature"]
            processed.append(thinking_block)

        elif block_type == "tool_use":
            processed.append({
                "type": "tool_use",
                "id": block.get("id", ""),
                "name": block.get("name", ""),
                "input": block.get("input", {})
            })

        elif block_type == "tool_result":
            # Keep FULL content for KV cache compatibility
            # Include is_error field if present
            result = {
                "tool_use_id": block.get("tool_use_id", ""),
                "type": "tool_result",
                "content": block.get("content", ""),
            }
            if "is_error" in block:
                result["is_error"] = block["is_error"]
            processed.append(result)

    # Do NOT simplify - keep exact structure for cache compatibility
    return processed


def jsonl_to_yaml(session_id: str) -> str:
    """Convert Claude Code JSONL to YAML format."""
    jsonl_path = find_jsonl(session_id)
    records = parse_jsonl(jsonl_path)
    records["_session_id"] = session_id

    meta = extract_metadata(records, jsonl_path)
    messages = convert_messages(records)

    # Build YAML structure
    doc = {
        "id": meta["id"],
        "source": meta["source"],
        "created": meta["created"],
        "project": meta["project"],
        "branch": meta["branch"],
        "summary": meta["summary"],
        "tags": meta["tags"],
        "messages": messages,
    }

    # Custom YAML dump for readability
    return yaml.dump(doc, default_flow_style=False, allow_unicode=True, sort_keys=False)


def yaml_to_jsonl(yaml_path: Path) -> list:
    """Convert YAML back to Claude Code JSONL format."""
    import uuid

    with open(yaml_path) as f:
        doc = yaml.safe_load(f)

    records = []
    session_id = doc["id"]

    # Add system record (required for Claude Code)
    system_record = {
        "type": "system",
        "subtype": "init",
        "cwd": doc.get("project", ""),
        "sessionId": session_id,
        "gitBranch": doc.get("branch", ""),
        "timestamp": doc.get("created", ""),
        "uuid": str(uuid.uuid4()),
    }
    records.append(system_record)

    # Reconstruct user/assistant records
    for i, msg in enumerate(doc.get("messages", [])):
        role = msg["role"]
        content = msg["content"]

        # Convert content back to API format
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

        record = {
            "type": role,
            "message": {
                "role": role,
                "content": api_content
            },
            "sessionId": session_id,
            "timestamp": msg.get("ts"),
            "uuid": str(uuid.uuid4()),
        }
        records.append(record)

    return records


def yaml_to_api_messages(yaml_path: Path) -> list:
    """Convert YAML to API messages format (for continuation)."""
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
                    # Thinking blocks need signature for API
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

        messages.append({"role": role, "content": api_content})

    return messages


def test_roundtrip(session_id: str):
    """Test bidirectional conversion."""
    print(f"Testing round-trip for session: {session_id}")

    # Step 1: JSONL -> YAML
    print("\n1. Converting JSONL -> YAML...")
    jsonl_path = find_jsonl(session_id)
    yaml_content = jsonl_to_yaml(session_id)

    yaml_path = Path(f"/tmp/test_{session_id[:8]}.yaml")
    with open(yaml_path, "w") as f:
        f.write(yaml_content)

    print(f"   Written to: {yaml_path}")
    print(f"   YAML size: {len(yaml_content):,} bytes")

    # Show first 50 lines
    lines = yaml_content.split("\n")
    print(f"   First 30 lines:")
    for line in lines[:30]:
        print(f"   {line}")

    # Step 2: YAML -> API messages
    print("\n2. Converting YAML -> API messages...")
    api_messages = yaml_to_api_messages(yaml_path)
    print(f"   Message count: {len(api_messages)}")
    print(f"   Roles: {[m['role'] for m in api_messages[:10]]}...")

    # Step 3: Compare original message count
    print("\n3. Comparing with original...")
    records = parse_jsonl(jsonl_path)
    orig_user = len(records["user"])
    orig_asst = len(records["assistant"])

    yaml_user = sum(1 for m in api_messages if m["role"] == "user")
    yaml_asst = sum(1 for m in api_messages if m["role"] == "assistant")

    print(f"   Original: {orig_user} user, {orig_asst} assistant")
    print(f"   YAML:     {yaml_user} user, {yaml_asst} assistant")

    if orig_user == yaml_user and orig_asst == yaml_asst:
        print("\n✓ Round-trip successful! Message counts match.")
    else:
        print("\n✗ Message count mismatch!")

    # Step 4: Size comparison
    print("\n4. Size comparison...")
    jsonl_size = jsonl_path.stat().st_size
    yaml_size = yaml_path.stat().st_size
    reduction = (1 - yaml_size / jsonl_size) * 100
    print(f"   JSONL: {jsonl_size:,} bytes")
    print(f"   YAML:  {yaml_size:,} bytes")
    print(f"   Reduction: {reduction:.1f}%")

    return yaml_path


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1]
    arg = sys.argv[2]

    if cmd == "jsonl2yaml":
        print(jsonl_to_yaml(arg))
    elif cmd == "yaml2jsonl":
        records = yaml_to_jsonl(Path(arg))
        for rec in records:
            print(json.dumps(rec))
    elif cmd == "test":
        test_roundtrip(arg)
    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)
