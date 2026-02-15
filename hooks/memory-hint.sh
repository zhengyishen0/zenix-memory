#!/bin/bash
# Memory hint hook - shows relevant past sessions for user's question
# Runs on first message of session

ZENIX_ROOT="${ZENIX_ROOT:-$HOME/.zenix}"

INPUT=$(cat)
PROMPT=$(echo "$INPUT" | jq -r '.prompt')
SESSION_ID=$(echo "$INPUT" | jq -r '.session_id')

# Skip if prompt too short
[ ${#PROMPT} -lt 15 ] && exit 0

# Check if this is first message (no transcript yet or very small)
TRANSCRIPT=$(echo "$INPUT" | jq -r '.transcript_path')
if [ -f "$TRANSCRIPT" ] && [ $(wc -l < "$TRANSCRIPT") -gt 5 ]; then
  exit 0  # Not first message, skip
fi

# Run memory hint
HINTS=$("$ZENIX_ROOT/skills/core/memory/hint.sh" "$PROMPT" 2>/dev/null)

if [ -n "$HINTS" ]; then
  echo "<memory-hint>"
  echo "$HINTS"
  echo "</memory-hint>"
fi

exit 0
