#!/usr/bin/env python3
"""Auto-discover domain keywords via co-occurrence analysis.

Analyzes the memory index to find words that frequently co-occur with
known seed keywords. These are likely domain-specific terms that should
be added to the custom keywords list.

Strategy:
1. Start with seed keywords (known domain terms)
2. Find messages containing seed keywords
3. Extract other words that frequently co-occur
4. Filter by frequency threshold and not in general stopwords
5. Write to data/custom_keywords.txt

Usage:
    python3 build_custom_keywords.py           # Analyze and suggest
    python3 build_custom_keywords.py --write   # Write to file

Run weekly or after significant index growth.
"""

import sys
import re
import math
from pathlib import Path
from collections import Counter, defaultdict

# Try to import jieba
try:
    import jieba
    jieba.setLogLevel(jieba.logging.INFO)
    JIEBA_AVAILABLE = True
except ImportError:
    JIEBA_AVAILABLE = False

SCRIPT_DIR = Path(__file__).parent
SKILL_DIR = SCRIPT_DIR.parent
INDEX_FILE = SKILL_DIR / 'data' / 'memory-index.tsv'
OUTPUT_FILE = SKILL_DIR / 'data' / 'custom_keywords.txt'
ENGLISH_FREQ_FILE = SKILL_DIR / 'data' / 'english_freq.txt'

# English frequency data (loaded lazily)
_english_freq = None
_english_total = None

# Seed keywords - known domain terms to find co-occurrences with
SEED_KEYWORDS = {
    # English
    'feishu', 'lark', 'bitable', 'oauth', 'chrome', 'browser', 'cdp',
    'headless', 'playwright', 'automation', 'calendar', 'gmail', 'api',
    # Chinese
    '飞书', '多维表格', '审批', '浏览器', '自动化', '日历', '机器人',
}

# General stopwords - extensive list to filter out generic words
GENERAL_STOPWORDS = {
    # Common English
    'the', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been', 'being',
    'to', 'for', 'of', 'in', 'on', 'at', 'by', 'with', 'from', 'as',
    'and', 'or', 'but', 'if', 'then', 'else', 'this', 'that', 'it',
    'you', 'we', 'they', 'have', 'has', 'had', 'do', 'does', 'did',
    'will', 'would', 'can', 'could', 'should', 'may', 'might', 'must',
    'not', 'no', 'yes', 'just', 'also', 'only', 'more', 'some', 'any',
    'all', 'each', 'every', 'both', 'few', 'many', 'much', 'most',
    'other', 'such', 'same', 'new', 'first', 'last', 'next', 'right',
    'now', 'then', 'here', 'there', 'when', 'where', 'why', 'how',
    'what', 'which', 'who', 'whom', 'whose', 'one', 'two', 'three',
    'your', 'our', 'their', 'its', 'into', 'about', 'after', 'before',
    # Tech generic
    'use', 'used', 'using', 'uses', 'file', 'files', 'code', 'like',
    'need', 'get', 'got', 'make', 'made', 'set', 'see', 'look', 'find',
    'run', 'running', 'test', 'error', 'message', 'result', 'value',
    'data', 'name', 'type', 'text', 'line', 'time', 'user', 'path',
    'search', 'bash', 'memory', 'session', 'sessions', 'tool', 'tools',
    'work', 'works', 'working', 'let', 'key', 'summary', 'full',
    'messages', 'current', 'results', 'output', 'without', 'start',
    'open', 'format', 'based', 'via', 'command', 'setup', 'mode', 'add',
    'system', 'access', 'call', 'calls', 'check', 'show', 'process',
    'com', 'www', 'http', 'https', 'nmemory', 'nthe', 'nif', 'nsearch',
    'function', 'method', 'class', 'object', 'string', 'number', 'list',
    'input', 'response', 'request', 'query', 'params', 'args', 'options',
    'config', 'default', 'true', 'false', 'null', 'none', 'return',
    'load', 'save', 'parse', 'build', 'generate', 'extract', 'convert',
    'handle', 'execute', 'implement', 'import', 'export', 'module',
    'version', 'example', 'testing', 'debug', 'log', 'print', 'display',
    # Conversation words
    'help', 'please', 'thanks', 'want', 'trying', 'going', 'doing',
    'think', 'know', 'question', 'questions', 'answer', 'problem', 'issue', 'solution',
    'idea', 'way', 'thing', 'something', 'anything', 'everything',
    # Generic English adjectives/adverbs
    'simple', 'better', 'good', 'best', 'great', 'nice', 'fine', 'easy',
    'hard', 'difficult', 'fast', 'slow', 'quick', 'small', 'large', 'big',
    'old', 'long', 'short', 'high', 'low', 'full', 'empty', 'available',
    'optional', 'required', 'relevant', 'useful', 'different', 'similar',
    # Generic English verbs (past/participle)
    'added', 'updated', 'changed', 'created', 'removed', 'deleted', 'moved',
    'done', 'made', 'found', 'written', 'read', 'called', 'defined',
    # Generic nouns
    'words', 'terms', 'names', 'types', 'items', 'elements', 'parts',
    'design', 'structure', 'pattern', 'patterns', 'style', 'styles',
    'docs', 'documentation', 'readme', 'guide', 'tutorial', 'reference',
    # More generic
    'etc', 'through', 'out', 'top', 'wants', 'native', 'complex',
    'nthis', 'nthat', 'nif', 'nthe', 'natural', 'language', 'matches',
    'primary', 'multi', 'control', 'recommendation', 'date', 'filter',
    'auto', 'pass', 'flag', 'dev', 'commands',
    # Claude Code specific (generic in this context)
    'claude', 'agent', 'agents', 'task', 'tasks', 'context', 'prompt',
    'hint', 'hints', 'keyword', 'keywords', 'topics', 'topic',
    'extraction', 'architecture', 'implementation', 'workflow', 'approach',
    # Chinese common
    '的', '地', '得', '了', '着', '过', '吗', '呢', '啊', '吧', '呀',
    '我', '你', '他', '她', '它', '我们', '你们', '他们', '这', '那',
    '是', '有', '没有', '不', '会', '能', '可以', '要', '想', '做',
    '看', '说', '知道', '帮', '帮我', '请', '什么', '怎么', '为什么',
    '很', '太', '最', '更', '就', '才', '都', '也', '还', '又', '再',
    '个', '些', '点', '下', '次', '好', '行', '那', '然后',
}

# Minimum frequency to consider a word as a candidate
MIN_FREQUENCY = 5

# Minimum co-occurrence count with seed keywords
MIN_COOCCURRENCE = 3


def load_index():
    """Load messages from the memory index."""
    if not INDEX_FILE.exists():
        print(f"Error: Index file not found: {INDEX_FILE}", file=sys.stderr)
        print("Run 'memory search' first to build the index.", file=sys.stderr)
        sys.exit(1)

    messages = []
    with open(INDEX_FILE, 'r', encoding='utf-8') as f:
        for line in f:
            parts = line.rstrip('\n').split('\t')
            if len(parts) >= 4:
                session_id, timestamp, msg_type, text = parts[:4]
                messages.append({
                    'session_id': session_id,
                    'text': text,
                })
    return messages


def extract_words(text):
    """Extract words from text (both English and Chinese)."""
    words = set()

    # English words (3+ chars)
    en_words = re.findall(r'\b[a-zA-Z]{3,}\b', text.lower())
    words.update(en_words)

    # Chinese words (using jieba if available)
    zh_text = ''.join(re.findall(r'[\u4e00-\u9fff]+', text))
    if zh_text:
        if JIEBA_AVAILABLE:
            zh_words = [w for w in jieba.lcut(zh_text) if len(w) >= 2]
            words.update(zh_words)
        else:
            # Fallback: bigrams
            for i in range(len(zh_text) - 1):
                words.add(zh_text[i:i+2])

    return words


def find_cooccurrences(messages):
    """Find words that co-occur with seed keywords.

    Optimized: Only extract words (expensive jieba) for messages containing seeds.
    Global counts use fast English-only extraction for all messages.
    """
    # Count global word frequency (English only - fast)
    global_counts = Counter()

    # Count co-occurrences with each seed keyword
    cooccurrence = defaultdict(Counter)

    # Pre-compute lowercase seeds for faster matching
    seed_patterns = [(s, s.lower()) for s in SEED_KEYWORDS]

    for msg in messages:
        text = msg['text']
        text_lower = text.lower()

        # Fast global count: English words only (no jieba)
        en_words = re.findall(r'\b[a-zA-Z]{3,}\b', text_lower)
        global_counts.update(en_words)

        # Check which seed keywords appear in this message
        matching_seeds = set()
        for seed, seed_low in seed_patterns:
            if seed_low in text_lower or seed in text:
                matching_seeds.add(seed)

        # Only extract full words (with jieba) for messages with seeds
        if matching_seeds:
            words = extract_words(text)
            # Also add Chinese words to global counts
            for w in words:
                if not w.isascii():
                    global_counts[w] += 1

            for word in words:
                for seed in matching_seeds:
                    if word.lower() != seed.lower() and word != seed:
                        cooccurrence[seed][word] += 1

    return global_counts, cooccurrence


_jieba_initialized = False


def _init_jieba():
    """Initialize jieba dictionary (lazy load)."""
    global _jieba_initialized
    if _jieba_initialized or not JIEBA_AVAILABLE:
        return
    # Force jieba to load its dictionary
    jieba.lcut("初始化")
    _jieba_initialized = True


def get_jieba_freq(word):
    """Get word frequency from jieba's built-in dictionary.

    Returns a normalized frequency (0-1) or None if not found.
    High frequency in jieba = common word in general Chinese.
    """
    if not JIEBA_AVAILABLE:
        return None
    try:
        _init_jieba()
        # jieba.dt.FREQ is a dict of word -> frequency
        freq = jieba.dt.FREQ.get(word, 0)
        # Normalize by total (jieba.dt.total is sum of all frequencies)
        if freq > 0 and jieba.dt.total > 0:
            return freq / jieba.dt.total
        return None
    except Exception:
        return None


def _load_english_freq():
    """Load English word frequencies from file (once)."""
    global _english_freq, _english_total
    if _english_freq is not None:
        return

    _english_freq = {}
    _english_total = 0

    if not ENGLISH_FREQ_FILE.exists():
        return

    try:
        with open(ENGLISH_FREQ_FILE, 'r', encoding='utf-8') as f:
            for line in f:
                parts = line.strip().split()
                if len(parts) >= 2:
                    word = parts[0].lower()
                    try:
                        freq = int(parts[1])
                        _english_freq[word] = freq
                        _english_total += freq
                    except ValueError:
                        continue
    except Exception:
        pass


def get_english_freq(word):
    """Get word frequency from English frequency file.

    Returns a normalized frequency (0-1) or None if not found.
    High frequency = common word in general English.
    """
    global _english_freq, _english_total
    _load_english_freq()

    if not _english_freq or _english_total == 0:
        return None

    freq = _english_freq.get(word.lower(), 0)
    if freq > 0:
        return freq / _english_total
    return None


def is_english_word(word):
    """Check if word is English (ASCII letters only)."""
    return bool(re.match(r'^[a-zA-Z]+$', word))


def score_candidates(global_counts, cooccurrence, total_messages):
    """Score candidate keywords using PMI + domain specificity.

    Two-factor scoring:
    1. PMI: How much more likely does this word appear with seeds vs random?
    2. Domain specificity: Is this word rare in general Chinese but common here?
    """
    candidates = Counter()
    seed_lower = {s.lower() for s in SEED_KEYWORDS}

    # Count messages containing any seed keyword
    total_corpus_words = sum(global_counts.values())

    for seed, cooc_counts in cooccurrence.items():
        seed_total = sum(cooc_counts.values())  # Total words co-occurring with this seed

        for word, count in cooc_counts.items():
            if count < MIN_COOCCURRENCE:
                continue
            # Skip stopwords
            if word.lower() in GENERAL_STOPWORDS or word in GENERAL_STOPWORDS:
                continue
            # Skip seed keywords themselves
            if word.lower() in seed_lower or word in SEED_KEYWORDS:
                continue

            # Factor 1: PMI-like score
            # P(word|seed) = count / seed_total
            # P(word) = global_count / total_corpus_words
            # PMI = log2(P(word|seed) / P(word))
            global_freq = global_counts.get(word, 1)
            p_word_given_seed = count / max(seed_total, 1)
            p_word = global_freq / max(total_corpus_words, 1)

            if p_word > 0 and p_word_given_seed > p_word:
                pmi = math.log2(p_word_given_seed / p_word)
            else:
                pmi = 0

            # Factor 2: Domain specificity
            # Compare our corpus frequency to general frequency
            # Use English freq for English words, jieba for Chinese
            if is_english_word(word):
                general_freq = get_english_freq(word)
            else:
                general_freq = get_jieba_freq(word)

            if general_freq is not None and general_freq > 0:
                our_freq = global_freq / max(total_corpus_words, 1)
                # If our frequency is 10x higher than general, boost the score
                domain_boost = min(10, our_freq / general_freq) if our_freq > general_freq else 0.5
            else:
                # Word not in frequency dict = likely domain-specific or proper noun
                # Give significant boost to these
                domain_boost = 8 if global_freq >= 10 else 2

            # Combined score
            # PMI identifies co-occurrence patterns
            # domain_boost identifies domain-specific vocabulary
            score = count * (1 + pmi) * domain_boost

            candidates[word] += score

    return candidates


def load_existing_keywords():
    """Load existing custom keywords."""
    existing = set()
    if OUTPUT_FILE.exists():
        with open(OUTPUT_FILE, 'r', encoding='utf-8') as f:
            for line in f:
                word = line.strip()
                if word and not word.startswith('#'):
                    existing.add(word)
    return existing


def main():
    write_mode = '--write' in sys.argv

    print("=" * 60)
    print("Custom Keyword Discovery via Co-occurrence")
    print("=" * 60)
    print()

    # Load index
    print("Loading index...")
    messages = load_index()
    print(f"  {len(messages)} messages loaded")
    print()

    # Find co-occurrences
    print("Analyzing co-occurrences with seed keywords...")
    print(f"  Seeds: {', '.join(list(SEED_KEYWORDS)[:10])}...")
    global_counts, cooccurrence = find_cooccurrences(messages)
    print()

    # Score candidates
    print("Scoring candidates with PMI + domain specificity...")
    candidates = score_candidates(global_counts, cooccurrence, len(messages))
    print()

    # Load existing
    existing = load_existing_keywords()

    # Show top candidates
    print("=" * 60)
    print("TOP CANDIDATE KEYWORDS")
    print("=" * 60)
    print()

    new_keywords = []
    for word, score in candidates.most_common(50):
        if word in existing:
            status = "(already in list)"
        else:
            status = "NEW"
            new_keywords.append(word)
        freq = global_counts.get(word, 0)
        print(f"  {word:<20} score={score:.1f}  freq={freq}  {status}")

    print()
    print(f"Found {len(new_keywords)} new candidate keywords")
    print()

    if write_mode:
        # Write to file
        print("=" * 60)
        print(f"Writing to {OUTPUT_FILE}")
        print("=" * 60)

        # Combine existing + new (top 30)
        all_keywords = sorted(existing | set(new_keywords[:30]))

        OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
            f.write("# Custom keywords for memory hint\n")
            f.write("# Auto-generated by build_custom_keywords.py\n")
            f.write("# One keyword per line\n")
            f.write("#\n")
            for word in all_keywords:
                f.write(f"{word}\n")

        print(f"  Wrote {len(all_keywords)} keywords")
        print()
    else:
        print("Run with --write to save to file:")
        print(f"  python3 {Path(__file__).name} --write")
        print()


if __name__ == '__main__':
    main()
