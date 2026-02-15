---
name: memory
description: Search and recall from previous Claude Code sessions. Use when user asks about past conversations, previous work, or needs to find something discussed before.
---

# Memory Tool

Search across all Claude Code sessions like a hive mind.

## Quick Start

```bash
# Step 1: Search to explore
memory search "browser automation"

# Step 2: If snippets answer your question, you're done!

# Step 3: If you need deeper answers, use --recall
memory search "browser click" --recall "how to click a button by text?"
```

## Commands

```bash
# Search for sessions (start here)
memory search "keyword1 keyword2"

# If snippets aren't enough, recall with a question
memory search "keywords" --recall "specific question?"
```

## Search Modes

### Simple Mode (default)

Space-separated keywords, OR logic, ranked by matches:

```bash
memory search "chrome automation workflow"
```

- Matches ANY keyword (broad search)
- Sessions matching more keywords rank higher
- Best for exploratory searches

### Strict Mode (pipes)

Use pipes (`|`) for OR within groups, spaces for AND between groups:

```bash
memory search "chrome|browser automation|workflow"
```

- Must match at least one term from EACH group
- Best when you need specific term combinations

## Options

| Flag | Description | Default |
|------|-------------|---------|
| `--sessions N` | Number of sessions to return | 10 |
| `--messages N` | Messages per session to show | 5 |
| `--context N` | Characters of context per snippet | 300 |
| `--recall "Q"` | Ask matching sessions a question | - |

**Phrase support:** Use underscore to join words: `reset_windows` matches "reset windows"

## When to Use

- User asks: "What did we discuss about X?"
- User asks: "How did we solve Y before?"
- User asks: "Find that session where we..."
- Need context from previous work

## Key Principles

1. **Search first, recall second** - Snippets often contain enough info
2. **Refine before recall** - Good keywords = good recall results
3. **Simple by default** - Just list keywords, no special syntax needed
4. **Incremental indexing** - Full index on first run (~12s), incremental after (~0.5s)

## Technical Details

**Index location:** `~/.claude/memory-index.tsv`

**Format:** `session_id\ttimestamp\ttype\ttext_preview\tproject_path`

**Requirements:**
- ripgrep (rg) - Fast text search
- jq - JSON processing
- Python 3 - Result formatting
