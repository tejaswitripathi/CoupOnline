"""Empirical Gemini-mimic agent (hard tier).

Reuses `EmpiricalAgent` from `easy1.py` but replays Gemini's recorded decisions
instead of Claude's. Gemini is the strongest model in the dataset (highest win
rate), which is why this is the "hard" tier. See `easy1.py` for how the
nearest-neighbour softmax policy works.
"""

try:
    from .easy1 import EmpiricalAgent, _smoke_test
except ImportError:
    from easy1 import EmpiricalAgent, _smoke_test


class EmpiricalGeminiAgent(EmpiricalAgent):
    """Empirical policy that mimics the recorded Gemini agent."""

    model = "gemini-empirical"
    source_model = "gemini-3.1-flash-lite"
    label = "Gemini"


if __name__ == "__main__":
    _smoke_test(EmpiricalGeminiAgent)
