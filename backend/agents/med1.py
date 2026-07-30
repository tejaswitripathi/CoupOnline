"""Empirical GPT-mimic agent (medium tier).

Reuses `EmpiricalAgent` from `easy1.py` but replays GPT's recorded decisions
instead of Claude's. See `easy1.py` for how the nearest-neighbour softmax
policy works.
"""

try:
    from .easy1 import EmpiricalAgent, _smoke_test
except ImportError:
    from easy1 import EmpiricalAgent, _smoke_test


class EmpiricalGPTAgent(EmpiricalAgent):
    """Empirical policy that mimics the recorded GPT agent."""

    model = "gpt-empirical"
    source_model = "gpt-5.4-nano"
    label = "GPT"


if __name__ == "__main__":
    _smoke_test(EmpiricalGPTAgent)
