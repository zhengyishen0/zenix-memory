#!/bin/zsh
# Memory hint - auto-extract keywords from natural language and search
# Used by session start hooks to provide context hints
#
# Usage:
#   memory hint "help me debug the feishu approval workflow"
#   memory hint "帮我看看飞书审批的问题"
#
# Output: Session headers with related topics
#   [short-id] keyword1[count] keyword2[count] (N matches | date) → topic1, topic2, topic3

set -eo pipefail

SCRIPT_DIR="${0:A:h}"
SKILL_DIR="$(dirname "$SCRIPT_DIR")"
LIB_DIR="$SKILL_DIR/lib"

show_help() {
  cat << 'EOF'
memory hint - Auto-extract keywords and search for relevant sessions

USAGE
  memory hint "<natural language query>"

DESCRIPTION
  Extracts keywords from natural language (English, Chinese, or mixed)
  and searches memory for relevant sessions. Shows related topics
  extracted from matched messages.

EXAMPLES
  memory hint "help me debug the browser automation"
  memory hint "飞书审批流程有问题"
  memory hint "feishu API 调用失败"

OUTPUT FORMAT
  [short-id] keyword1[N] keyword2[M] (X matches | date) → topic1, topic2, topic3

  Topics show what else was discussed in each session (excluding search terms).

EOF
}

if [ $# -eq 0 ] || [ "$1" = "--help" ] || [ "$1" = "-h" ]; then
  show_help
  exit 0
fi

TEXT="$*"

# Extract keywords using hint_keywords.py
KEYWORDS=$(python3 "$LIB_DIR/hint_keywords.py" "$TEXT" 2>/dev/null)

if [ -z "$KEYWORDS" ]; then
  # No keywords extracted, nothing to search
  exit 0
fi

# Search with topics enabled by default
"$SCRIPT_DIR/search.sh" "$KEYWORDS" --messages 0 --sessions 5 --topics 2>/dev/null | grep -v "^Found matches\|^Tip:\|^$"
