"""Multi-dimensional behavioural variation metrics."""

import math
import re
from typing import Set, List


class VariationMetrics:
    """Calculates behavioural, structural, and semantic distance between coding tasks."""

    @staticmethod
    def jaccard_distance(set_a: Set[str], set_b: Set[str]) -> float:
        if not set_a and not set_b:
            return 0.0
        union = set_a.union(set_b)
        if not union:
            return 0.0
        intersection = set_a.intersection(set_b)
        return 1.0 - (len(intersection) / len(union))

    @staticmethod
    def text_cosine_similarity(text_a: str, text_b: str) -> float:
        """Compute bag-of-words cosine similarity between two texts."""
        words_a = re.findall(r"\b[a-z]{3,}\b", text_a.lower())
        words_b = re.findall(r"\b[a-z]{3,}\b", text_b.lower())

        vocab = set(words_a).union(words_b)
        if not vocab:
            return 1.0

        vec_a = [words_a.count(w) for w in vocab]
        vec_b = [words_b.count(w) for w in vocab]

        dot = sum(a * b for a, b in zip(vec_a, vec_b))
        mag_a = math.sqrt(sum(a * a for a in vec_a))
        mag_b = math.sqrt(sum(b * b for b in vec_b))

        if mag_a == 0 or mag_b == 0:
            return 0.0
        return dot / (mag_a * mag_b)

    @classmethod
    def calculate_behavioural_distance(
        cls,
        tags_a: List[str],
        tags_b: List[str],
        files_a: List[str],
        files_b: List[str],
        text_a: str,
        text_b: str,
    ) -> float:
        """Calculates normalized distance 0.0 (identical) to 1.0 (completely distinct)."""
        j_tags = cls.jaccard_distance(set(tags_a), set(tags_b))
        j_files = cls.jaccard_distance(set(files_a), set(files_b))
        cosine_sim = cls.text_cosine_similarity(text_a, text_b)
        text_dist = 1.0 - cosine_sim

        # 4-factor distance: 40% tags, 30% files, 30% semantic text
        distance = (0.40 * j_tags) + (0.30 * j_files) + (0.30 * text_dist)
        return round(min(1.0, max(0.0, distance)), 3)

