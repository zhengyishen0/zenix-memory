#!/usr/bin/env python3
"""Fast formatting of memory search results using pure Python (no pandas).

Two modes:
- simple: Rank by keyword hits -> match count -> recency
- strict: Rank by match count -> recency (hits not relevant since AND-filtered)

Uses pre-normalized index for NLP matching with zero query-time overhead.
Index format: session_id | timestamp | type | text | text_normalized | project_path

Optimized: Removed pandas dependency for 2.5x faster startup.
"""

import sys
import os
import re
from collections import defaultdict, Counter
from pathlib import Path

# Try to import jieba for Chinese segmentation
try:
    import jieba
    jieba.setLogLevel(jieba.logging.INFO)  # Suppress loading messages
    JIEBA_AVAILABLE = True
except ImportError:
    JIEBA_AVAILABLE = False


def shorten_path(path):
    """Replace $HOME with ~"""
    home = str(Path.home())
    return path.replace(home, "~")


# English stopwords for topic extraction
STOPWORDS_EN = {
    # Articles, prepositions, conjunctions
    'the', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been', 'being',
    'to', 'for', 'of', 'in', 'on', 'at', 'by', 'with', 'from', 'as',
    'and', 'or', 'but', 'if', 'then', 'else', 'when', 'where', 'why',
    'how', 'what', 'which', 'who', 'whom', 'whose',
    # Pronouns
    'i', 'me', 'my', 'we', 'us', 'our', 'you', 'your', 'he', 'him', 'his',
    'she', 'her', 'it', 'its', 'they', 'them', 'their', 'this', 'that',
    'these', 'those',
    # Common verbs
    'do', 'does', 'did', 'done', 'have', 'has', 'had', 'get', 'got',
    'make', 'made', 'go', 'went', 'take', 'took', 'come', 'came',
    'see', 'saw', 'know', 'knew', 'think', 'thought', 'want', 'need',
    'try', 'use', 'used', 'find', 'found', 'give', 'gave', 'tell', 'told',
    'say', 'said', 'let', 'put', 'keep', 'kept', 'seem', 'leave', 'left',
    'call', 'ask', 'work', 'look', 'run', 'read', 'write', 'show',
    'add', 'set', 'create', 'update', 'delete', 'remove', 'change',
    'start', 'stop', 'open', 'close', 'send', 'receive',
    # Modals
    'can', 'could', 'will', 'would', 'shall', 'should', 'may', 'might', 'must',
    # Adverbs
    'just', 'also', 'only', 'still', 'even', 'now', 'then', 'here', 'there',
    'very', 'really', 'well', 'back', 'much', 'more', 'most', 'some', 'any',
    'out', 'up', 'down', 'off', 'away',
    # Fillers
    'please', 'thanks', 'thank', 'help', 'okay', 'yes', 'no', 'not',
    'about', 'after', 'before', 'into', 'over', 'under', 'again',
    # Quantifiers
    'all', 'each', 'every', 'both', 'few', 'many', 'other', 'new', 'first',
    'last', 'next', 'right', 'wrong', 'way', 'thing', 'something',
    'one', 'two', 'three',
    # Common tech words (too generic)
    'file', 'files', 'code', 'like', 'using', 'been', 'data', 'name',
    'function', 'return', 'true', 'false', 'null', 'none', 'import',
    'class', 'def', 'self', 'var', 'let', 'const', 'type', 'string', 'int',
    'error', 'message', 'result', 'value', 'key', 'list', 'item', 'items',
    'user', 'users', 'test', 'example', 'default', 'output', 'input',
    'path', 'url', 'com', 'org', 'www', 'https', 'http',
}

# Chinese stopwords for topic extraction
STOPWORDS_ZH = {
    # Particles
    '的', '地', '得', '了', '着', '过', '吗', '呢', '啊', '吧', '呀', '哦',
    # Pronouns
    '我', '你', '您', '他', '她', '它', '我们', '你们', '他们', '她们',
    '这', '那', '这个', '那个', '这些', '那些', '这里', '那里',
    # Conjunctions, prepositions
    '和', '与', '或', '但', '但是', '因为', '所以', '如果', '虽然',
    '在', '从', '到', '对', '向', '把', '被', '给', '跟', '比',
    '里', '里面', '上', '下', '前', '后',
    # Common verbs
    '是', '有', '没有', '没', '不', '不是', '会', '能', '可以', '要', '想',
    '做', '去', '来', '说', '看', '知道', '觉得', '认为', '希望',
    '看看', '想要', '有个', '是不是', '能不能',
    '帮', '帮我', '帮忙', '请', '请问', '试试', '用',
    # Question words
    '什么', '怎么', '怎样', '为什么', '哪', '哪个', '哪些', '哪里', '谁', '多少',
    # Adverbs
    '很', '太', '真', '最', '更', '非常', '特别', '比较',
    '就', '才', '都', '也', '还', '又', '再', '已经', '正在', '一直',
    # Measure words
    '个', '些', '点', '下', '次', '种', '样', '一', '一个', '一下', '一些',
    # Fillers
    '好', '行', '可以', '好的', '那', '然后', '接下来',
    '问题', '情况', '方法', '东西', '事情',
}

# Custom words for jieba
CUSTOM_WORDS_ZH = [
    '飞书', '多维表格', '审批流程', '机器人',
    '浏览器', '自动化', '日历', '同步',
]

_jieba_initialized = False

def _init_jieba():
    """Initialize jieba with custom words (only once)."""
    global _jieba_initialized
    if _jieba_initialized or not JIEBA_AVAILABLE:
        return
    for word in CUSTOM_WORDS_ZH:
        jieba.add_word(word)
    _jieba_initialized = True


def extract_topics(texts, exclude_keywords, max_topics=4):
    """Extract top keywords from texts, excluding search keywords.

    Uses jieba for Chinese segmentation, simple regex for English.

    Args:
        texts: List of text strings to extract from
        exclude_keywords: Set of keywords to exclude (the search terms)
        max_topics: Maximum number of topics to return

    Returns:
        List of (keyword, count) tuples
    """
    word_counts = Counter()
    exclude_lower = {k.lower() for k in exclude_keywords}

    # Initialize jieba if available
    if JIEBA_AVAILABLE:
        _init_jieba()

    for text in texts:
        # Extract English words (3+ chars)
        en_words = re.findall(r'\b[a-zA-Z]{3,}\b', text.lower())
        for word in en_words:
            if word not in STOPWORDS_EN and word not in exclude_lower:
                word_counts[word] += 1

        # Extract Chinese segments
        zh_text = ''.join(re.findall(r'[\u4e00-\u9fff]+', text))
        if zh_text:
            if JIEBA_AVAILABLE:
                # Use jieba for proper segmentation
                words = jieba.lcut(zh_text)
                for word in words:
                    if len(word) >= 2 and word not in STOPWORDS_ZH and word not in exclude_lower:
                        word_counts[word] += 1
            else:
                # Fallback: character bigrams
                for i in range(len(zh_text) - 1):
                    bigram = zh_text[i:i+2]
                    if bigram not in STOPWORDS_ZH and bigram not in exclude_lower:
                        word_counts[bigram] += 1

    # Return top N by count
    return word_counts.most_common(max_topics)


def get_keyword_counts(text, text_normalized, keywords, keywords_normalized):
    """Return dict of keyword -> occurrence count in text.

    Uses word boundary matching on normalized text for ASCII keywords.
    For non-ASCII (Chinese, etc.), searches original text directly.
    """
    counts = {}

    for keyword, keyword_norm in zip(keywords, keywords_normalized):
        if not keyword.isascii():
            # Non-ASCII (Chinese, etc.): search original text, no word boundary
            matches = re.findall(re.escape(keyword), text, re.IGNORECASE)
        else:
            # ASCII: word boundary match on normalized text
            pattern = rf'\b{re.escape(keyword_norm)}\b'
            matches = re.findall(pattern, text_normalized, re.IGNORECASE)

        if matches:
            counts[keyword] = len(matches)

    return counts


def count_keyword_hits(text, text_normalized, keywords, keywords_normalized):
    """Count how many unique keywords appear in the text."""
    return len(get_keyword_counts(text, text_normalized, keywords, keywords_normalized))


def parse_keywords(query, mode):
    """Extract keywords from query based on mode."""
    if mode == 'strict':
        terms = []
        for group in query.split():
            terms.extend(group.split('|'))
        return [t.lower() for t in terms]
    else:
        return [k.lower() for k in query.split()]


def extract_snippet(text, text_normalized, keywords, keywords_normalized, context):
    """Extract snippet around a matched keyword if text is long."""
    if len(text) <= context:
        return text

    text_lower = text.lower()
    pos = -1

    # Try to find keyword in original text first
    for keyword in keywords:
        pattern = keyword.replace('_', '.')
        match = re.search(pattern, text_lower, re.IGNORECASE)
        if match:
            pos = match.start()
            break

    # If not found, find via normalized text word position
    if pos < 0:
        words = text_lower.split()
        norm_words = text_normalized.split()

        for keyword_norm in keywords_normalized:
            if keyword_norm in norm_words:
                idx = norm_words.index(keyword_norm)
                # Map normalized word index to character position in original
                if idx < len(words):
                    pos = sum(len(w) + 1 for w in words[:idx])
                break

    if pos >= 0:
        before = context // 3
        after = context - before
        start = max(0, pos - before)
        end = min(len(text), pos + after)
        snippet = text[start:end]
        if start > 0:
            snippet = "..." + snippet
        if end < len(text):
            snippet = snippet + "..."
        return snippet
    else:
        return text[:context] + "..."


def main():
    if len(sys.argv) < 6:
        print("Usage: format-results.py <sessions> <messages> <context> <query> <mode> [query_normalized] [--topics]", file=sys.stderr)
        sys.exit(1)

    sessions_limit = int(sys.argv[1])
    messages_limit = int(sys.argv[2])
    context = int(sys.argv[3])
    query = sys.argv[4]
    mode = sys.argv[5]
    query_normalized = sys.argv[6] if len(sys.argv) > 6 else query.lower()
    show_topics = '--topics' in sys.argv

    keywords = parse_keywords(query, mode)
    keywords_normalized = query_normalized.lower().split()

    # Exclude current session from search results
    current_session_id = os.environ.get('CLAUDE_SESSION_ID', '')

    sessions = defaultdict(dict)
    for line in sys.stdin:
        parts = line.rstrip('\n').split('\t', 5)
        if len(parts) == 6:
            session_id, timestamp, msg_type, text, text_normalized, project_path = parts
            # Skip current session
            if current_session_id and session_id == current_session_id:
                continue
            key = (timestamp, msg_type, text)
            if key not in sessions[session_id]:
                sessions[session_id][key] = {
                    'timestamp': timestamp,
                    'type': msg_type,
                    'text': text,
                    'text_normalized': text_normalized,
                    'project_path': project_path
                }

    if not sessions:
        print("No matches found.")
        return

    session_stats = []
    for session_id, msgs_dict in sessions.items():
        msgs = list(msgs_dict.values())

        for msg in msgs:
            msg['keyword_counts'] = get_keyword_counts(
                msg['text'], msg['text_normalized'], keywords, keywords_normalized
            )
            msg['keyword_hits'] = len(msg['keyword_counts'])

        session_keyword_counts = defaultdict(int)
        for msg in msgs:
            for kw, count in msg['keyword_counts'].items():
                session_keyword_counts[kw] += count

        hits = len(session_keyword_counts) if mode == 'simple' else 0
        max_ts = max(m['timestamp'] for m in msgs)

        # Calculate weighted score: first keyword = n, last keyword = 1
        # This prioritizes core keywords (listed first) over less confident ones
        weighted_score = 0
        n = len(keywords)
        for i, kw in enumerate(keywords):
            weight = n - i  # First keyword gets highest weight
            weighted_score += session_keyword_counts.get(kw, 0) * weight

        session_stats.append({
            'session_id': session_id,
            'hits': hits,
            'matches': len(msgs),
            'weighted_score': weighted_score,
            'timestamp': max_ts,
            'project_path': msgs[0]['project_path'],
            'messages': msgs,
            'keyword_counts': dict(session_keyword_counts)
        })

    if mode == 'simple':
        # Rank by weighted score (core keywords matter more), then hits, then matches
        session_stats.sort(key=lambda x: (x['weighted_score'], x['hits'], x['matches'], x['timestamp']), reverse=True)
    else:
        session_stats = [s for s in session_stats if s['matches'] >= 5]
        session_stats.sort(key=lambda x: (x['matches'], x['timestamp']), reverse=True)

    # Auto-cutoff: 70% cumulative score, min=3, max=8
    if session_stats:
        total_score = sum(s['weighted_score'] for s in session_stats)
        cumsum = 0
        cutoff_idx = 0
        for i, s in enumerate(session_stats):
            cumsum += s['weighted_score']
            cutoff_idx = i + 1
            if cumsum >= total_score * 0.7:
                break
        # Apply min/max bounds
        cutoff_idx = max(3, min(8, cutoff_idx))
        session_stats = session_stats[:cutoff_idx]
    else:
        session_stats = session_stats[:sessions_limit]

    total_sessions = len(session_stats)
    total_keywords = len(keywords)

    for s in session_stats:
        short_id = s['session_id'][:8]  # First 8 chars (enough for recall)
        project = shorten_path(s['project_path'])
        matches = s['matches']
        date = s['timestamp'][:10]

        kw_counts = s['keyword_counts']
        kw_parts = ' '.join(f"{kw}[{kw_counts[kw]}]" for kw in keywords if kw in kw_counts)

        # Extract topics if requested
        if show_topics:
            texts = [m['text'] for m in s['messages']]
            topics = extract_topics(texts, set(keywords), max_topics=4)
            if topics:
                topic_str = ', '.join(t[0] for t in topics)
                print(f"[{short_id}] {kw_parts} ({matches} matches | {date}) → {topic_str}")
            else:
                print(f"[{short_id}] {kw_parts} ({matches} matches | {date} | {project})")
        else:
            print(f"[{short_id}] {kw_parts} ({matches} matches | {date} | {project})")

        if messages_limit > 0:
            sorted_msgs = sorted(s['messages'], key=lambda m: m['keyword_hits'], reverse=True)
            for msg in sorted_msgs[:messages_limit]:
                role = "[user]" if msg['type'] == 'user' else "[asst]"
                text = extract_snippet(
                    msg['text'], msg['text_normalized'], keywords, keywords_normalized, context
                )
                print(f"{role} {text}")

            if matches > messages_limit:
                print(f"... and {matches - messages_limit} more matches")

            print()

    if mode == 'simple':
        print(f"\nFound matches in {total_sessions} sessions (searched {total_keywords} keywords)")
    else:
        print(f"\nFound matches in {total_sessions} sessions (strict mode)")

    session_ids = [s['session_id'][:8] for s in session_stats]  # Short IDs work for recall
    print(','.join(session_ids), file=sys.stderr)


if __name__ == '__main__':
    main()
