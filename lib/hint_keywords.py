#!/usr/bin/env python3
"""Extract search keywords from natural language input.

Handles mixed English/Chinese text. Used by memory hint system to
automatically generate search queries from user messages.

Custom keywords are loaded from data/custom_keywords.txt (one per line).
Run build_custom_keywords.py to auto-discover domain keywords via co-occurrence.

Usage:
    python3 hint_keywords.py "help me debug the feishu approval workflow"
    python3 hint_keywords.py "帮我看看飞书审批的问题"
    python3 hint_keywords.py "feishu 审批流程 有问题"
"""

import re
import sys
from pathlib import Path

# Try to import jieba for Chinese segmentation
try:
    import jieba
    jieba.setLogLevel(jieba.logging.INFO)  # Suppress loading messages
    JIEBA_AVAILABLE = True
except ImportError:
    JIEBA_AVAILABLE = False

SCRIPT_DIR = Path(__file__).parent
SKILL_DIR = SCRIPT_DIR.parent
CUSTOM_KEYWORDS_FILE = SKILL_DIR / 'data' / 'custom_keywords.txt'

# Minimum word length for English (filters out 'am', 'pc', 're', etc.)
MIN_ENGLISH_WORD_LENGTH = 3

# English stopwords - common words that don't help search
STOPWORDS_EN = {
    # Articles, prepositions, conjunctions
    'the', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been', 'being',
    'to', 'for', 'of', 'in', 'on', 'at', 'by', 'with', 'from', 'as',
    'and', 'or', 'but', 'if', 'then', 'else', 'when', 'where', 'why',
    'how', 'what', 'which', 'who', 'whom', 'whose',
    # Pronouns
    'i', 'me', 'my', 'mine', 'we', 'us', 'our', 'ours',
    'you', 'your', 'yours', 'he', 'him', 'his', 'she', 'her', 'hers',
    'it', 'its', 'they', 'them', 'their', 'theirs',
    'this', 'that', 'these', 'those',
    # Common verbs (too generic)
    'do', 'does', 'did', 'done', 'doing',
    'have', 'has', 'had', 'having',
    'get', 'got', 'getting', 'gets',
    'make', 'made', 'making', 'makes',
    'go', 'went', 'going', 'goes', 'gone',
    'take', 'took', 'taking', 'takes', 'taken',
    'come', 'came', 'coming', 'comes',
    'see', 'saw', 'seeing', 'sees', 'seen',
    'know', 'knew', 'knowing', 'knows', 'known',
    'think', 'thought', 'thinking', 'thinks',
    'want', 'wanted', 'wanting', 'wants',
    'need', 'needed', 'needing', 'needs',
    'try', 'tried', 'trying', 'tries',
    'use', 'used', 'using', 'uses',
    'find', 'found', 'finding', 'finds',
    'give', 'gave', 'giving', 'gives', 'given',
    'tell', 'told', 'telling', 'tells',
    'say', 'said', 'saying', 'says',
    'let', 'lets', 'letting',
    'put', 'puts', 'putting',
    'keep', 'kept', 'keeping', 'keeps',
    'begin', 'began', 'beginning', 'begins', 'begun',
    'seem', 'seemed', 'seeming', 'seems',
    'leave', 'left', 'leaving', 'leaves',
    'call', 'called', 'calling', 'calls',
    'ask', 'asked', 'asking', 'asks',
    'work', 'worked', 'working', 'works',
    'look', 'looked', 'looking', 'looks',
    # Action verbs (common in commands but not useful for search)
    'fix', 'fixed', 'fixing', 'fixes',
    'add', 'added', 'adding', 'adds',
    'show', 'showed', 'showing', 'shows', 'shown',
    'check', 'checked', 'checking', 'checks',
    'debug', 'debugged', 'debugging', 'debugs',
    'run', 'ran', 'running', 'runs',
    'start', 'started', 'starting', 'starts',
    'stop', 'stopped', 'stopping', 'stops',
    'open', 'opened', 'opening', 'opens',
    'close', 'closed', 'closing', 'closes',
    'read', 'reading', 'reads',
    'write', 'wrote', 'writing', 'writes', 'written',
    'create', 'created', 'creating', 'creates',
    'delete', 'deleted', 'deleting', 'deletes',
    'update', 'updated', 'updating', 'updates',
    'change', 'changed', 'changing', 'changes',
    'set', 'setting', 'sets',
    'move', 'moved', 'moving', 'moves',
    'copy', 'copied', 'copying', 'copies',
    'send', 'sent', 'sending', 'sends',
    'remember', 'remembered', 'remembering', 'remembers',
    'continue', 'continued', 'continuing', 'continues',
    # Modal verbs
    'can', 'could', 'will', 'would', 'shall', 'should',
    'may', 'might', 'must',
    # Common adverbs
    'just', 'also', 'only', 'still', 'even', 'again',
    'now', 'then', 'here', 'there', 'very', 'really',
    'well', 'back', 'much', 'more', 'most', 'less', 'least',
    'off', 'out', 'up', 'down', 'away',
    # Filler words
    'please', 'thanks', 'thank', 'help', 'okay', 'ok', 'yes', 'no',
    'maybe', 'perhaps', 'actually', 'basically', 'probably',
    # Other common words
    'about', 'after', 'before', 'between', 'through', 'during',
    'into', 'over', 'under', 'above', 'below',
    'some', 'any', 'all', 'each', 'every', 'both', 'few', 'many',
    'other', 'another', 'such', 'same', 'different',
    'first', 'last', 'next', 'new', 'old', 'good', 'bad',
    'right', 'wrong', 'way', 'thing', 'things', 'something',
    'anything', 'nothing', 'everything',
    # Short words that are usually not useful
    'am', 'an', 're', 'oh', 'so', 'no', 'hi', 'ah',
}

# Chinese stopwords - common particles and function words
STOPWORDS_ZH = {
    # Particles
    '的', '地', '得', '了', '着', '过', '吗', '呢', '啊', '吧', '呀', '哦', '嘛', '啦',
    # Pronouns
    '我', '你', '您', '他', '她', '它', '我们', '你们', '他们', '她们', '它们',
    '这', '那', '这个', '那个', '这些', '那些', '这里', '那里',
    # Conjunctions, prepositions
    '和', '与', '或', '但', '但是', '因为', '所以', '如果', '虽然',
    '在', '从', '到', '对', '向', '把', '被', '给', '跟', '比',
    # Location/direction words
    '里', '里面', '外', '外面', '上', '上面', '下', '下面', '前', '前面', '后', '后面',
    # Common verbs (too generic)
    '是', '有', '没有', '没', '不', '不是', '会', '能', '可以', '要', '想', '应该',
    '做', '去', '来', '说', '看', '知道', '觉得', '认为', '希望',
    '看看', '想要', '有个', '是不是', '能不能', '可不可以', '不能',
    '帮', '帮我', '帮忙', '请', '请问',
    '试试', '想想', '看下', '看一下', '弄', '搞', '整',
    '无法', '不对', '不行', '不好', '好像', '可能', '应该',
    '执行', '添加', '讨论', '使用',
    # Time references (not useful for keyword search)
    '之前', '之后', '以前', '以后', '上次', '下次', '刚才', '现在', '马上',
    '今天', '明天', '昨天', '时候',
    # Question words
    '什么', '怎么', '怎样', '为什么', '哪', '哪个', '哪些', '哪里', '谁', '多少',
    # Adverbs
    '很', '太', '真', '最', '更', '非常', '特别', '比较', '稍微',
    '就', '才', '都', '也', '还', '又', '再', '已经', '正在', '一直',
    '还是', '先', '不管', '不要',
    # Measure words and numbers
    '个', '些', '点', '下', '次', '种', '样', '一', '一个', '一下', '一些', '一点',
    # Filler
    '好', '行', '可以', '好的', '那', '然后', '接下来',
}

# Built-in custom words - technical terms that should not be split
# Additional words come from data/custom_keywords.txt
BUILTIN_CUSTOM_WORDS = [
    # Feishu/Lark
    '飞书', '多维表格', '审批流程', '机器人', '群聊',
    # Browser automation
    '浏览器', '自动化', '无头模式',
    # Calendar/sync
    '日历', '同步', '日历同步',
    # Common tech terms
    '配置文件', '命令行', '接口调用',
]


def load_custom_keywords():
    """Load custom keywords from file + built-in list."""
    keywords = list(BUILTIN_CUSTOM_WORDS)
    if CUSTOM_KEYWORDS_FILE.exists():
        try:
            with open(CUSTOM_KEYWORDS_FILE, 'r', encoding='utf-8') as f:
                for line in f:
                    word = line.strip()
                    if word and not word.startswith('#'):
                        if word not in keywords:
                            keywords.append(word)
        except Exception:
            pass
    return keywords


def has_cjk(text):
    """Check if text contains CJK (Chinese/Japanese/Korean) characters."""
    return bool(re.search(r'[\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff]', text))


def extract_english_keywords(text):
    """Extract keywords from English text."""
    keywords = []

    # Find all word-like sequences (letters only, MIN_ENGLISH_WORD_LENGTH+ chars)
    words = re.findall(rf'\b[a-zA-Z]{{{MIN_ENGLISH_WORD_LENGTH},}}\b', text.lower())

    # Filter stopwords
    keywords.extend(w for w in words if w not in STOPWORDS_EN)

    # Also extract 3+ digit numbers (like 404, 500, 502)
    numbers = re.findall(r'\b\d{3,}\b', text)
    keywords.extend(numbers)

    return keywords


_jieba_initialized = False
_custom_keywords = None


def _init_jieba():
    """Initialize jieba with custom words (only once)."""
    global _jieba_initialized, _custom_keywords
    if _jieba_initialized or not JIEBA_AVAILABLE:
        return
    _custom_keywords = load_custom_keywords()
    for word in _custom_keywords:
        jieba.add_word(word)
    _jieba_initialized = True


def extract_chinese_keywords(text):
    """Extract keywords from Chinese text."""
    if JIEBA_AVAILABLE:
        _init_jieba()
        # Use jieba for proper word segmentation
        words = jieba.lcut(text)
        # Filter: must be 2+ chars and not stopword
        keywords = [w for w in words if len(w) >= 2 and w not in STOPWORDS_ZH]
    else:
        # Fallback: character bigrams (less accurate but no dependency)
        # Remove punctuation first
        clean = re.sub(r'[^\u4e00-\u9fff]', '', text)
        keywords = [clean[i:i+2] for i in range(len(clean)-1) if clean[i:i+2] not in STOPWORDS_ZH]

    return keywords


def extract_keywords(text, max_keywords=6):
    """Extract search keywords from mixed-language text.

    Args:
        text: User input (can be English, Chinese, or mixed)
        max_keywords: Maximum number of keywords to return

    Returns:
        List of keywords, ordered by appearance (first = most important)
    """
    if not text or not text.strip():
        return []

    keywords = []

    # Split text into CJK and non-CJK segments
    # This regex captures CJK runs as separate groups
    segments = re.split(r'([\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff]+)', text)

    for segment in segments:
        if not segment or not segment.strip():
            continue

        if has_cjk(segment):
            keywords.extend(extract_chinese_keywords(segment))
        else:
            keywords.extend(extract_english_keywords(segment))

    # Deduplicate while preserving order
    seen = set()
    unique_keywords = []
    for kw in keywords:
        if kw not in seen:
            seen.add(kw)
            unique_keywords.append(kw)

    # Return first N keywords (first ones are usually more important)
    return unique_keywords[:max_keywords]


def main():
    """CLI interface for keyword extraction."""
    if len(sys.argv) < 2:
        print("Usage: hint_keywords.py <text>", file=sys.stderr)
        print("       echo <text> | hint_keywords.py", file=sys.stderr)
        sys.exit(1)

    if len(sys.argv) > 1 and sys.argv[1] != '-':
        text = ' '.join(sys.argv[1:])
    else:
        text = sys.stdin.read()

    keywords = extract_keywords(text)

    if keywords:
        print(' '.join(keywords))


if __name__ == '__main__':
    main()
