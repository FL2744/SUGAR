"""Optional, reproducible English lexical indicators of expressed language.

These exploratory axes are not a validated emotion classifier or a measure of a
person's mental state. Unsupported language and missing lexical evidence abstain.
Translation-based scores retain their basis; no remote model or service is used.
"""
from __future__ import annotations

import re
from typing import Any

METHOD = "sugar-english-lexicon-v1"
NOTE = ("Exploratory English lexical indicators, including English translations. "
        "Valence: −1 negative to +1 positive; intensity: 0 to 1; direction: −1 self-referential to +1 other-directed. "
        "Missing evidence is unscored. Negation is approximate; sarcasm and cultural context require review. "
        "These scores are not validated emotional or psychological judgments.")
_POSITIVE = {w: 1 for w in "good great happy hope hopeful joy joyful love welcome welcomed trust proud pleased support supportive success successful benefit beneficial peace peaceful grateful gratitude opportunity opportunities celebrate celebration improve improved progress excited inspiring excellent wonderful".split()}
_NEGATIVE = {w: -1 for w in "bad sad sadness fear fearful afraid anger angry hate hatred harm harmful failure failed crisis violent violence worry worried threat threats suffering suffer grief disappointed terrible awful hostile hostility tragic tragedy abuse corruption injustice".split()}
_WEIGHTS = {**_POSITIVE, **_NEGATIVE, "love": 2, "hate": -2, "excellent": 2, "terrible": -2, "awful": -2, "wonderful": 2}
_NEGATORS = {"not", "no", "never", "neither", "hardly", "without", "isn't", "wasn't", "don't", "doesn't", "didn't", "can't", "cannot"}
_BOOSTERS = {"very", "extremely", "deeply", "really", "so", "absolutely"}
_INWARD = {"i", "me", "my", "mine", "myself", "we", "us", "our", "ours", "ourselves"}
_OUTWARD = {"you", "your", "yours", "yourself", "they", "them", "their", "theirs", "he", "him", "his", "she", "her", "hers"}


def score_text(text: str, *, language: str, basis: str = "original") -> dict[str, Any]:
    result: dict[str, Any] = {"method": METHOD, "basis": basis, "status": "unscored", "reason": "unsupported_language",
                              "valence": None, "intensity": None, "direction": None, "matched_terms": []}
    if language.casefold() not in {"en", "eng", "english"}:
        return result
    tokens = re.findall(r"[a-z]+(?:'[a-z]+)?|[.!?;,]", (text or "").casefold().replace("’", "'"))
    words = [t for t in tokens if t[0].isalpha()]
    if len(words) < 3:
        result["reason"] = "insufficient_text"
        return result
    values: list[float] = []
    context: list[str] = []
    for token in tokens:
        if token in ".!?;,":
            context = []
            continue
        weight = _WEIGHTS.get(token)
        if weight:
            sign = -1 if sum(t in _NEGATORS for t in context[-3:]) % 2 else 1
            strength = 1.5 if any(t in _BOOSTERS for t in context[-2:]) else 1
            values.append(weight * sign * strength)
            result["matched_terms"].append(token)
        context.append(token)
    inward, outward = sum(w in _INWARD for w in words), sum(w in _OUTWARD for w in words)
    if inward + outward:
        result["direction"] = round((outward - inward) / (inward + outward), 4)
    if values:
        result["valence"] = round(sum(values) / sum(abs(v) for v in values), 4)
        result["intensity"] = round(min(1, sum(abs(v) for v in values) / (2 * len(values)) + min(text.count("!"), 3) * .05), 4)
    result["matched_terms"] = sorted(set(result["matched_terms"]))
    result.update(status="scored" if values or inward + outward else "unscored", reason="" if values or inward + outward else "no_lexical_evidence")
    return result


def score_item(item: Any) -> dict[str, Any]:
    if str(item.language or "").casefold() in {"en", "eng", "english"}:
        return score_text(item.original_text, language="en")
    tr = item.translation if isinstance(item.translation, dict) else {}
    if tr.get("status") == "done" and str(tr.get("target_language", "")).casefold() in {"en", "eng", "english"}:
        return score_text(str(tr.get("text") or ""), language="en", basis="english_translation")
    return score_text(item.original_text, language=item.language or "und")
