from difflib import SequenceMatcher
import nltk

nltk.download('punkt_tab', quiet=True)

def sentence_sequence_delta(old_text: str, new_text: str) -> float:
    """
    Computes a dissimilarity score (Δ) between two texts using sentence-level alignment.
    Returns a float in [0,1], where 0 = identical, 1 = completely different.
    """
    old_sents = nltk.sent_tokenize(old_text)
    new_sents = nltk.sent_tokenize(new_text)

    matcher = SequenceMatcher(None, old_sents, new_sents)
    ratio = matcher.ratio()
    delta = 1.0 - ratio
    return round(delta, 4)

