"""
Utility functions for mathematical operations and content generation.

This module contains pure functions with no domain dependencies.
All functions are stateless and can be used across different modules.
"""

import math


def linear(score: float) -> float:
    """Linear activation function - returns input unchanged."""
    return score


def sigmoid(score: float, k: float = 5.0) -> float:
    """Sigmoid activation function for more decisive behavior at extremes."""
    return 1 / (1 + math.exp(-k * (score - 0.5)))


# Registry of available activation functions
ACTIVATIONS = {
    "linear": linear,
    "sigmoid": sigmoid,
}


def generate_lorem_content(rng, word_count=60):
    """Generate lorem ipsum content for testing purposes.

    Args:
        rng: Random number generator instance
        word_count: Number of words to generate (default: 60)

    Returns:
        str: Generated lorem ipsum text
    """
    words = [
        "lorem",
        "ipsum",
        "dolor",
        "sit",
        "amet",
        "consectetur",
        "adipiscing",
        "elit",
        "sed",
        "do",
        "eiusmod",
        "tempor",
        "incididunt",
        "ut",
        "labore",
        "et",
        "dolore",
        "magna",
        "aliqua",
        "enim",
        "ad",
        "minim",
        "veniam",
        "quis",
        "nostrud",
        "exercitation",
        "ullamco",
        "laboris",
        "nisi",
        "aliquip",
        "ex",
        "ea",
        "commodo",
        "consequat",
        "duis",
        "aute",
        "irure",
        "in",
        "reprehenderit",
        "voluptate",
        "velit",
        "esse",
        "cillum",
        "fugiat",
        "nulla",
        "pariatur",
        "excepteur",
        "sint",
        "occaecat",
        "cupidatat",
        "non",
        "proident",
        "sunt",
        "culpa",
        "qui",
        "officia",
        "deserunt",
        "mollit",
        "anim",
        "id",
        "est",
        "laborum",
        "suscipit",
        "lobortis",
        "nisl",
        "aliquam",
        "erat",
        "volutpat",
        "blandit",
        "praesent",
        "zzril",
        "delenit",
        "augue",
        "feugait",
        "facilisi",
        "diam",
        "nonummy",
        "nibh",
        "euismod",
        "tincidunt",
    ]
    return " ".join(rng.choices(words, k=word_count))
