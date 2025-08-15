from __future__ import annotations
import math, secrets, string, random
from typing import List, Tuple

# Characters often confused visually
_SIMILAR = set("Il1O0oS5Z2B8G6")
# Punctuation that could be ambiguous in some contexts
_AMBIGUOUS = set("{}[]()/\\'\"`~,;:.<>")

def build_charsets(
    use_lower: bool = True,
    use_upper: bool = True,
    use_digits: bool = True,
    use_symbols: bool = False,
    exclude_similar: bool = True,
    exclude_ambiguous: bool = False,
) -> Tuple[List[list[str]], list[str]]:
    """
    Returns (groups, combined) where:
      - groups: list of character groups enabled by options
      - combined: flattened unique alphabet across all enabled groups
    """
    groups: List[list[str]] = []

    if use_lower:
        g = set(string.ascii_lowercase)
        if exclude_similar: g -= (_SIMILAR & g)
        groups.append(sorted(g))
    if use_upper:
        g = set(string.ascii_uppercase)
        if exclude_similar: g -= (_SIMILAR & g)
        groups.append(sorted(g))
    if use_digits:
        g = set(string.digits)
        if exclude_similar: g -= (_SIMILAR & g)
        groups.append(sorted(g))
    if use_symbols:
        g = set(string.punctuation)
        if exclude_ambiguous: g -= _AMBIGUOUS
        groups.append(sorted(g))

    combined = sorted({c for grp in groups for c in grp})
    return groups, combined

def generate_one(length: int, groups: List[list[str]], combined: list[str]) -> str:
    """
    Generate a password of 'length' ensuring at least 1 char from each group.
    """
    if not groups or not combined:
        raise ValueError("No character sets selected.")
    if length < len(groups):
        raise ValueError("Length too short for the required groups.")

    sysrand = random.SystemRandom()
    pw_chars = [secrets.choice(grp) for grp in groups]  # guarantee coverage
    for _ in range(length - len(groups)):
        pw_chars.append(secrets.choice(combined))
    sysrand.shuffle(pw_chars)
    return "".join(pw_chars)

def entropy_bits(length: int, alphabet_size: int) -> float:
    if length <= 0 or alphabet_size <= 1:
        return 0.0
    return length * math.log2(alphabet_size)

def strength_label(bits: float) -> str:
    if bits < 50:  return "Weak"
    if bits < 80:  return "Fair"
    if bits < 110: return "Strong"
    return "Very strong"
