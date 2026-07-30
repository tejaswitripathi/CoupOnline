"""Empirical LLM-mimic agents.

Instead of calling an LLM, an empirical agent replays a recorded model's
behaviour. At each decision it looks up every decision that model made in
`database/coup_generated.sqlite3` under a *similar* game state, tallies which
move was chosen, and samples from a softmax over those tallies.

Because the dataset is small, "similar" is deliberately coarse. A state is
described by only three features:

  1. the model's current hand      (the multiset of its own cards)
  2. the model's current coin count
  3. the card count of every other live player (a multiset)

Matching degrades gracefully: it first requires all three features to match,
then relaxes them tier by tier until at least one legal move has support,
finally falling back to the model's global prior for the decision type.

`EmpiricalClaudeAgent` (this file) mimics Claude. `med1.py` and `hard1.py`
reuse `EmpiricalAgent` to mimic GPT and Gemini respectively.
"""

import json
import math
import random
import sqlite3
from collections import defaultdict
from pathlib import Path

try:
    from .base import safe_fallback_decision
except ImportError:
    from base import safe_fallback_decision


DB_PATH = Path(__file__).resolve().parent.parent / "database" / "coup_generated.sqlite3"

# Only used for the rare Exchange selection, which has too little data to learn.
CARD_STRENGTH = {"Duke": 5, "Captain": 4, "Assassin": 3, "Contessa": 2, "Ambassador": 1}


class EmpiricalAgent:
    """Nearest-neighbour policy that mimics a recorded model's decisions."""

    provider = "local"
    model = None          # this agent's own identity/label in a match
    source_model = None   # the recorded model to imitate (must be set)
    label = "Model"       # human-readable name used in rationale strings

    def __init__(
        self,
        db_path: str | Path | None = None,
        temperature: float = 1.0,
        seed: int | None = None,
    ):
        if not self.source_model:
            raise ValueError("EmpiricalAgent subclasses must set `source_model`.")
        self.db_path = Path(db_path) if db_path else DB_PATH
        self.temperature = temperature
        self._rng = random.Random(seed)
        # records[decision_type] -> list of feature/choice dicts.
        self._records: dict[str, list[dict]] = defaultdict(list)
        self._load_index()

    # ---- index building -------------------------------------------------

    def _load_index(self) -> None:
        if not self.db_path.exists():
            raise FileNotFoundError(f"Training data not found at {self.db_path}")

        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        try:
            snap_rows = conn.execute(
                "SELECT state_id, player_id, cards, num_coins FROM PlayerSnapshot"
            ).fetchall()
            decision_rows = conn.execute(
                "SELECT state_id, player_id, decision_type, action, raw_decision "
                "FROM Decision WHERE model = ?",
                (self.source_model,),
            ).fetchall()
        finally:
            conn.close()

        cards_by_state: dict = defaultdict(dict)
        coins_by_player: dict = {}
        cards_of_player: dict = {}
        for row in snap_rows:
            hand = json.loads(row["cards"]) if row["cards"] else []
            cards_by_state[row["state_id"]][row["player_id"]] = len(hand)
            coins_by_player[(row["state_id"], row["player_id"])] = row["num_coins"]
            cards_of_player[(row["state_id"], row["player_id"])] = hand

        for row in decision_rows:
            key = (row["state_id"], row["player_id"])
            my_hand = cards_of_player.get(key)
            if my_hand is None:
                continue

            dtype, choice = self._classify(row)
            if dtype is None:
                continue

            others = tuple(
                sorted(
                    count
                    for pid, count in cards_by_state[row["state_id"]].items()
                    if pid != row["player_id"] and count > 0
                )
            )
            self._records[dtype].append(
                {
                    "my_cards": tuple(sorted(my_hand)),
                    "my_coins": coins_by_player.get(key, 0),
                    "others": others,
                    "choice": choice,
                }
            )

    @staticmethod
    def _classify(row) -> tuple[str | None, object]:
        """Map a stored Decision row to (internal_type, chosen_move)."""
        dtype = row["decision_type"]
        action = row["action"]
        if dtype == "declare":
            return "declare", action
        if dtype == "response":
            return "response", action
        if dtype == "select_card":
            raw = json.loads(row["raw_decision"]) if row["raw_decision"] else {}
            if action == "Exchange":
                return "exchange", tuple(sorted(raw.get("keep_cards", [])))
            return "select_card_lose", raw.get("card")
        return None, None

    # ---- feature extraction from a live private_view --------------------

    @staticmethod
    def _query_features(private_view: dict) -> dict:
        history = private_view.get("history") or []
        snapshot = history[-1] if history else {}
        player_id = private_view.get("player_id")
        players = snapshot.get("players", [])

        me = next((p for p in players if p["id"] == player_id), None)
        my_coins = me["num_coins"] if me else 0
        my_cards = tuple(sorted((snapshot.get("private") or {}).get("cards", [])))
        others = tuple(
            sorted(
                p["num_cards"]
                for p in players
                if p["id"] != player_id and p["num_cards"] > 0
            )
        )
        return {"my_cards": my_cards, "my_coins": my_coins, "others": others}

    # ---- similarity tiers ----------------------------------------------

    @staticmethod
    def _tiers(query: dict):
        """Predicates from most to least specific over the 3 state features."""
        return [
            lambda r: r["my_cards"] == query["my_cards"]
            and r["my_coins"] == query["my_coins"]
            and r["others"] == query["others"],
            lambda r: r["my_cards"] == query["my_cards"] and r["others"] == query["others"],
            lambda r: r["my_cards"] == query["my_cards"],
            lambda r: r["others"] == query["others"],
            lambda r: True,
        ]

    def _tally(self, dtype: str, query: dict, legal: set):
        """Return (counts, tier) for the most specific tier with legal support."""
        records = self._records.get(dtype, [])
        for tier, predicate in enumerate(self._tiers(query)):
            counts: dict = defaultdict(int)
            for rec in records:
                if rec["choice"] in legal and predicate(rec):
                    counts[rec["choice"]] += 1
            if counts:
                return dict(counts), tier
        return {}, None

    # ---- softmax sampling ----------------------------------------------

    def _softmax_sample(self, counts: dict):
        # A literal softmax over raw counts overflows (dominant moves have ~1000
        # votes), so we sample proportional to count**(1/T): the Boltzmann
        # distribution whose T=1 case is exactly the model's empirical frequencies.
        if self.temperature <= 0:
            return max(counts, key=counts.get)

        exponent = 1.0 / self.temperature
        weights = {choice: count ** exponent for choice, count in counts.items()}
        total = math.fsum(weights.values())
        threshold = self._rng.random() * total
        cumulative = 0.0
        for choice, weight in weights.items():
            cumulative += weight
            if cumulative >= threshold:
                return choice
        return next(iter(weights))

    # ---- target / card heuristics --------------------------------------

    def _pick_target(self, declaration: dict, private_view: dict) -> int:
        valid = declaration.get("valid_target_ids") or []
        players = (private_view.get("history") or [{}])[-1].get("players", [])
        coins = {p["id"]: p["num_coins"] for p in players}
        # Target the wealthiest reachable opponent (biggest threat / best steal).
        return max(valid, key=lambda pid: (coins.get(pid, 0), -pid))

    def _exchange_keep(self, selection: dict) -> dict:
        candidates = list(selection.get("candidates") or [])
        keep_count = selection.get("keep_count", 0)
        # Learned combos are almost non-existent, so keep the strongest cards.
        ranked = sorted(candidates, key=lambda c: CARD_STRENGTH.get(c, 0), reverse=True)
        return {"command": "select_card", "keep_cards": ranked[:keep_count]}

    # ---- main entry point ----------------------------------------------

    def decide(self, private_view: dict, data_generation: bool = True) -> dict:
        legal_next = private_view.get("legal_next", {})
        query = self._query_features(private_view)

        decision, note = self._choose(legal_next, private_view, query)
        return self._result(decision, note, data_generation)

    def _choose(self, legal_next: dict, private_view: dict, query: dict):
        declarations = legal_next.get("declarations") or []
        responses = legal_next.get("responses") or []
        selection = legal_next.get("selection")

        if declarations:
            by_action = {d["action"]: d for d in declarations}
            counts, tier = self._tally("declare", query, set(by_action))
            if counts:
                action = self._softmax_sample(counts)
                decision = {"command": "declare", "action": action}
                if by_action[action].get("requires_target"):
                    decision["target_player_id"] = self._pick_target(by_action[action], private_view)
                return decision, self._note("declare", counts, tier)

        elif responses:
            counts, tier = self._tally("response", query, set(responses))
            if counts:
                response = self._softmax_sample(counts)
                return {"command": "respond", "response": response}, self._note("response", counts, tier)

        elif selection:
            if selection["kind"] == "lose_influence":
                cards = selection.get("cards", [])
                counts, tier = self._tally("select_card_lose", query, set(cards))
                if counts:
                    card = self._softmax_sample(counts)
                    return {"command": "select_card", "card": card}, self._note("discard", counts, tier)
            elif selection["kind"] == "exchange":
                return self._exchange_keep(selection), "exchange: kept strongest cards (sparse data)"

        return safe_fallback_decision(private_view), "no matching data; used safe fallback"

    # ---- output shaping ------------------------------------------------

    def _note(self, label: str, counts: dict, tier: int) -> str:
        total = sum(counts.values())
        return (
            f"Empirical {self.label} {label}: sampled from {total} similar "
            f"{self.label} decisions (tier {tier}); distribution={dict(counts)}"
        )

    def _result(self, decision: dict, note: str, data_generation: bool) -> dict:
        return {
            "provider": self.provider,
            "model": self.model,
            "decision": decision,
            "thoughts": note if data_generation else None,
            "private_thoughts": None if data_generation else note,
            "public_thoughts": None if data_generation else "I am playing my usual game.",
            "raw_output": decision,
            "fallback": note.startswith("no matching"),
        }


class EmpiricalClaudeAgent(EmpiricalAgent):
    """Empirical policy that mimics the recorded Claude agent (easy tier)."""

    model = "claude-empirical"
    source_model = "claude-haiku-4-5"
    label = "Claude"


def _smoke_test(agent_cls) -> None:
    agent = agent_cls()
    total = sum(len(v) for v in agent._records.values())
    print(f"[{agent.model}] indexed {total} {agent.label} decisions from {agent.db_path}")
    for dtype, records in agent._records.items():
        print(f"  {dtype}: {len(records)}")

    sample_view = {
        "player_id": 3,
        "history": [
            {
                "private": {"player_id": 3, "cards": ["Contessa", "Ambassador"]},
                "players": [
                    {"id": 1, "num_coins": 3, "num_cards": 2},
                    {"id": 2, "num_coins": 2, "num_cards": 1},
                    {"id": 3, "num_coins": 2, "num_cards": 2},
                ],
            }
        ],
        "legal_next": {
            "declarations": [
                {"action": "Income", "requires_target": False, "valid_target_ids": []},
                {"action": "Tax", "requires_target": False, "valid_target_ids": []},
                {"action": "Steal", "requires_target": True, "valid_target_ids": [1, 2]},
                {"action": "Exchange", "requires_target": False, "valid_target_ids": []},
            ],
            "responses": [],
            "selection": None,
        },
    }
    result = agent.decide(sample_view, data_generation=True)
    print("Sample decision:", result["decision"])
    print("Rationale:", result["thoughts"])


if __name__ == "__main__":
    _smoke_test(EmpiricalClaudeAgent)
