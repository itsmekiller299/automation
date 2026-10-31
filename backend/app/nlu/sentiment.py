from __future__ import annotations

import re

FRUSTRATION_TERMS = {
    "angry",
    "frustrated",
    "frustrating",
    "furious",
    "ridiculous",
    "unacceptable",
    "useless",
    "pathetic",
    "scam",
    "fraud",
    "worst",
    "terrible",
    "horrible",
    "sick of",
    "fed up",
    "cancel everything",
    "speak to your manager",
    "sue",
    "bakwas",
    "ghatiya",
    "faltu",
    "pagal",
    "kya bakwaas",
    "bahut kharab",
    "cheating",
    "dhokha",
}


def detect_frustration(text: str) -> tuple[bool, list[str]]:
    normalized = text.lower().strip()
    matches = sorted({term for term in FRUSTRATION_TERMS if term in normalized})
    if matches:
        return True, matches
    # Shouting is a weaker signal; only treat a reasonably long all-caps
    # message as frustration to avoid flagging acronyms and order IDs.
    letters = [char for char in text if char.isalpha()]
    if len(letters) >= 18:
        uppercase_ratio = sum(char.isupper() for char in letters) / len(letters)
        if uppercase_ratio > 0.85:
            return True, ["all_caps"]
    if len(text.split()) >= 5 and re.search(r"[!?]{4,}", text):
        return True, ["repeated_punctuation"]
    return False, []
