#!/usr/bin/env python3
"""Fast query normalizer using PyStemmer + irregular verbs table.

Uses Snowball stemmer for regular words (fast, no NLTK dependency).
Irregular verbs are handled via lookup table for accurate matching.

Example: "ran specifications" -> "run specif"
Note: "specifications" becomes "specif" (stemmed), which will match
other forms like "specify", "specific", "specification" in the index.
"""

import sys
import re

try:
    import Stemmer
    _stemmer = Stemmer.Stemmer('english')
    STEMMER_AVAILABLE = True
except ImportError:
    _stemmer = None
    STEMMER_AVAILABLE = False

# Common irregular verbs -> base form
# These don't follow regular stemming rules
IRREGULARS = {
    # be
    'was': 'be', 'were': 'be', 'been': 'be', 'being': 'be', 'am': 'be', 'is': 'be', 'are': 'be',
    # have
    'had': 'have', 'has': 'have', 'having': 'have',
    # do
    'did': 'do', 'does': 'do', 'doing': 'do', 'done': 'do',
    # go
    'went': 'go', 'goes': 'go', 'going': 'go', 'gone': 'go',
    # run
    'ran': 'run', 'running': 'run', 'runs': 'run',
    # say
    'said': 'say', 'says': 'say', 'saying': 'say',
    # make
    'made': 'make', 'makes': 'make', 'making': 'make',
    # take
    'took': 'take', 'takes': 'take', 'taking': 'take', 'taken': 'take',
    # come
    'came': 'come', 'comes': 'come', 'coming': 'come',
    # see
    'saw': 'see', 'sees': 'see', 'seeing': 'see', 'seen': 'see',
    # know
    'knew': 'know', 'knows': 'know', 'knowing': 'know', 'known': 'know',
    # get
    'got': 'get', 'gets': 'get', 'getting': 'get', 'gotten': 'get',
    # give
    'gave': 'give', 'gives': 'give', 'giving': 'give', 'given': 'give',
    # find
    'found': 'find', 'finds': 'find', 'finding': 'find',
    # think
    'thought': 'think', 'thinks': 'think', 'thinking': 'think',
    # tell
    'told': 'tell', 'tells': 'tell', 'telling': 'tell',
    # become
    'became': 'become', 'becomes': 'become', 'becoming': 'become',
    # leave
    'left': 'leave', 'leaves': 'leave', 'leaving': 'leave',
    # feel
    'felt': 'feel', 'feels': 'feel', 'feeling': 'feel',
    # bring
    'brought': 'bring', 'brings': 'bring', 'bringing': 'bring',
    # begin
    'began': 'begin', 'begins': 'begin', 'beginning': 'begin', 'begun': 'begin',
    # keep
    'kept': 'keep', 'keeps': 'keep', 'keeping': 'keep',
    # hold
    'held': 'hold', 'holds': 'hold', 'holding': 'hold',
    # write
    'wrote': 'write', 'writes': 'write', 'writing': 'write', 'written': 'write',
    # stand
    'stood': 'stand', 'stands': 'stand', 'standing': 'stand',
    # hear
    'heard': 'hear', 'hears': 'hear', 'hearing': 'hear',
    # mean
    'meant': 'mean', 'means': 'mean', 'meaning': 'mean',
    # meet
    'met': 'meet', 'meets': 'meet', 'meeting': 'meet',
    # pay
    'paid': 'pay', 'pays': 'pay', 'paying': 'pay',
    # sit
    'sat': 'sit', 'sits': 'sit', 'sitting': 'sit',
    # speak
    'spoke': 'speak', 'speaks': 'speak', 'speaking': 'speak', 'spoken': 'speak',
    # lead
    'led': 'lead', 'leads': 'lead', 'leading': 'lead',
    # read (irregular pronunciation, not spelling)
    'reads': 'read', 'reading': 'read',
    # grow
    'grew': 'grow', 'grows': 'grow', 'growing': 'grow', 'grown': 'grow',
    # lose
    'lost': 'lose', 'loses': 'lose', 'losing': 'lose',
    # fall
    'fell': 'fall', 'falls': 'fall', 'falling': 'fall', 'fallen': 'fall',
    # send
    'sent': 'send', 'sends': 'send', 'sending': 'send',
    # build
    'built': 'build', 'builds': 'build', 'building': 'build',
    # understand
    'understood': 'understand', 'understands': 'understand', 'understanding': 'understand',
    # draw
    'drawn': 'draw', 'drew': 'draw', 'draws': 'draw', 'drawing': 'draw',
    # break
    'broke': 'break', 'breaks': 'break', 'breaking': 'break', 'broken': 'break',
    # spend
    'spent': 'spend', 'spends': 'spend', 'spending': 'spend',
    # catch
    'caught': 'catch', 'catches': 'catch', 'catching': 'catch',
    # buy
    'bought': 'buy', 'buys': 'buy', 'buying': 'buy',
    # fight
    'fought': 'fight', 'fights': 'fight', 'fighting': 'fight',
    # teach
    'taught': 'teach', 'teaches': 'teach', 'teaching': 'teach',
    # sell
    'sold': 'sell', 'sells': 'sell', 'selling': 'sell',
    # seek
    'sought': 'seek', 'seeks': 'seek', 'seeking': 'seek',
    # throw
    'threw': 'throw', 'throws': 'throw', 'throwing': 'throw', 'thrown': 'throw',
    # show (partially irregular)
    'showed': 'show', 'shows': 'show', 'showing': 'show', 'shown': 'show',
    # choose
    'chose': 'choose', 'chooses': 'choose', 'choosing': 'choose', 'chosen': 'choose',
    # sleep
    'slept': 'sleep', 'sleeps': 'sleep', 'sleeping': 'sleep',
    # wear
    'worn': 'wear', 'wore': 'wear', 'wears': 'wear', 'wearing': 'wear',
    # win
    'won': 'win', 'wins': 'win', 'winning': 'win',
    # Common nouns
    'children': 'child', 'men': 'man', 'women': 'woman',
}


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


def normalize_query(text):
    """Normalize all words in query text.

    ASCII words: apply stemming
    Non-ASCII words (Chinese, etc.): pass through unchanged
    """
    # Split on whitespace to preserve non-ASCII words
    tokens = text.split()
    normalized = []
    for token in tokens:
        if token.isascii():
            # ASCII: extract word and stem it
            words = re.findall(r'\b[a-zA-Z]+\b', token)
            normalized.extend(normalize_word(w) for w in words)
        else:
            # Non-ASCII: pass through unchanged
            normalized.append(token)
    return ' '.join(normalized)


def main():
    if len(sys.argv) > 1:
        text = ' '.join(sys.argv[1:])
        print(normalize_query(text))
    else:
        for line in sys.stdin:
            line = line.rstrip('\n')
            if line:
                print(normalize_query(line))


if __name__ == '__main__':
    main()
