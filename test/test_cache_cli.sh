#!/bin/bash
# Test cache by resuming a session and checking token usage

SESSION_ID="$1"
if [ -z "$SESSION_ID" ]; then
    echo "Usage: $0 <session-id>"
    exit 1
fi

echo "Testing session: $SESSION_ID"
echo "Sending 'hi' to check if cache works..."
echo ""

# Resume session with a simple message, capture full output
OUTPUT=$(claude --resume "$SESSION_ID" --print "hi, just checking cache. reply OK only" 2>&1)

echo "Response:"
echo "$OUTPUT" | head -20
echo ""
echo "Check the token usage in Claude Code's output above."
echo "If cache_read_input_tokens > 0, cache is working."
