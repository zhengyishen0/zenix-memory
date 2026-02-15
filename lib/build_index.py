#!/usr/bin/env python3
"""Build memory search index with normalized text column.

Uses PyStemmer + irregular verbs table (same as normalize_query.py).
This ensures index and query normalization always match.

Input format:  session_id | timestamp | type | text | project_path
Output format: session_id | timestamp | type | text | text_normalized | project_path

Usage:
    python3 build_index.py < memory-index.tsv > memory-index-nlp.tsv
    python3 build_index.py input.tsv output.tsv
"""

import sys
import re
from functools import lru_cache

try:
    import Stemmer
    _stemmer = Stemmer.Stemmer('english')
    STEMMER_AVAILABLE = True
except ImportError:
    _stemmer = None
    STEMMER_AVAILABLE = False
    print("Warning: PyStemmer not available, using lowercase only", file=sys.stderr)

# Common irregular verbs -> base form (same as normalize_query.py)
IRREGULARS = {
    'was': 'be', 'were': 'be', 'been': 'be', 'being': 'be', 'am': 'be', 'is': 'be', 'are': 'be',
    'had': 'have', 'has': 'have', 'having': 'have',
    'did': 'do', 'does': 'do', 'doing': 'do', 'done': 'do',
    'went': 'go', 'goes': 'go', 'going': 'go', 'gone': 'go',
    'ran': 'run', 'running': 'run', 'runs': 'run',
    'said': 'say', 'says': 'say', 'saying': 'say',
    'made': 'make', 'makes': 'make', 'making': 'make',
    'took': 'take', 'takes': 'take', 'taking': 'take', 'taken': 'take',
    'came': 'come', 'comes': 'come', 'coming': 'come',
    'saw': 'see', 'sees': 'see', 'seeing': 'see', 'seen': 'see',
    'knew': 'know', 'knows': 'know', 'knowing': 'know', 'known': 'know',
    'got': 'get', 'gets': 'get', 'getting': 'get', 'gotten': 'get',
    'gave': 'give', 'gives': 'give', 'giving': 'give', 'given': 'give',
    'found': 'find', 'finds': 'find', 'finding': 'find',
    'thought': 'think', 'thinks': 'think', 'thinking': 'think',
    'told': 'tell', 'tells': 'tell', 'telling': 'tell',
    'became': 'become', 'becomes': 'become', 'becoming': 'become',
    'left': 'leave', 'leaves': 'leave', 'leaving': 'leave',
    'felt': 'feel', 'feels': 'feel', 'feeling': 'feel',
    'brought': 'bring', 'brings': 'bring', 'bringing': 'bring',
    'began': 'begin', 'begins': 'begin', 'beginning': 'begin', 'begun': 'begin',
    'kept': 'keep', 'keeps': 'keep', 'keeping': 'keep',
    'held': 'hold', 'holds': 'hold', 'holding': 'hold',
    'wrote': 'write', 'writes': 'write', 'writing': 'write', 'written': 'write',
    'stood': 'stand', 'stands': 'stand', 'standing': 'stand',
    'heard': 'hear', 'hears': 'hear', 'hearing': 'hear',
    'meant': 'mean', 'means': 'mean', 'meaning': 'mean',
    'met': 'meet', 'meets': 'meet', 'meeting': 'meet',
    'paid': 'pay', 'pays': 'pay', 'paying': 'pay',
    'sat': 'sit', 'sits': 'sit', 'sitting': 'sit',
    'spoke': 'speak', 'speaks': 'speak', 'speaking': 'speak', 'spoken': 'speak',
    'led': 'lead', 'leads': 'lead', 'leading': 'lead',
    'reads': 'read', 'reading': 'read',
    'grew': 'grow', 'grows': 'grow', 'growing': 'grow', 'grown': 'grow',
    'lost': 'lose', 'loses': 'lose', 'losing': 'lose',
    'fell': 'fall', 'falls': 'fall', 'falling': 'fall', 'fallen': 'fall',
    'sent': 'send', 'sends': 'send', 'sending': 'send',
    'built': 'build', 'builds': 'build', 'building': 'build',
    'understood': 'understand', 'understands': 'understand', 'understanding': 'understand',
    'drawn': 'draw', 'drew': 'draw', 'draws': 'draw', 'drawing': 'draw',
    'broke': 'break', 'breaks': 'break', 'breaking': 'break', 'broken': 'break',
    'spent': 'spend', 'spends': 'spend', 'spending': 'spend',
    'caught': 'catch', 'catches': 'catch', 'catching': 'catch',
    'bought': 'buy', 'buys': 'buy', 'buying': 'buy',
    'fought': 'fight', 'fights': 'fight', 'fighting': 'fight',
    'taught': 'teach', 'teaches': 'teach', 'teaching': 'teach',
    'sold': 'sell', 'sells': 'sell', 'selling': 'sell',
    'sought': 'seek', 'seeks': 'seek', 'seeking': 'seek',
    'threw': 'throw', 'throws': 'throw', 'throwing': 'throw', 'thrown': 'throw',
    'showed': 'show', 'shows': 'show', 'showing': 'show', 'shown': 'show',
    'chose': 'choose', 'chooses': 'choose', 'choosing': 'choose', 'chosen': 'choose',
    'slept': 'sleep', 'sleeps': 'sleep', 'sleeping': 'sleep',
    'worn': 'wear', 'wore': 'wear', 'wears': 'wear', 'wearing': 'wear',
    'won': 'win', 'wins': 'win', 'winning': 'win',
    'children': 'child', 'men': 'man', 'women': 'woman',
}


@lru_cache(maxsize=100000)
def normalize_word(word):
    """Normalize a single word using stemmer + irregular lookup."""
    if len(word) < 2:
        return word

    word_lower = word.lower()

    # Check irregular forms first
    if word_lower in IRREGULARS:
        return IRREGULARS[word_lower]

    # Use stemmer
    if STEMMER_AVAILABLE:
        return _stemmer.stemWord(word_lower)

    return word_lower


def normalize_text(text):
    """Normalize all words in text to stemmed forms."""
    # Extract words (alphanumeric sequences)
    words = re.findall(r'\b[a-zA-Z]+\b', text)

    # Normalize unique words first (deduplication for speed)
    unique_words = set(words)
    word_map = {w: normalize_word(w) for w in unique_words}

    # Build normalized text (just the normalized words, space-separated)
    normalized_words = [word_map[w] for w in words]
    return ' '.join(normalized_words)


def process_index(input_file, output_file):
    """Process index file, adding normalized text column."""
    line_count = 0

    for line in input_file:
        line = line.rstrip('\n')
        if not line:
            continue

        parts = line.split('\t')
        if len(parts) >= 5:
            session_id, timestamp, msg_type, text, project_path = parts[0], parts[1], parts[2], parts[3], parts[4]

            # Normalize the text
            text_normalized = normalize_text(text)

            # Output with normalized column inserted before project_path
            output_file.write(f"{session_id}\t{timestamp}\t{msg_type}\t{text}\t{text_normalized}\t{project_path}\n")

            line_count += 1
            if line_count % 10000 == 0:
                print(f"Processed {line_count} lines...", file=sys.stderr)

    print(f"Done. Processed {line_count} lines.", file=sys.stderr)


def main():
    if len(sys.argv) == 3:
        # File arguments
        with open(sys.argv[1], 'r') as infile, open(sys.argv[2], 'w') as outfile:
            process_index(infile, outfile)
    else:
        # Stdin/stdout
        process_index(sys.stdin, sys.stdout)


if __name__ == '__main__':
    main()
