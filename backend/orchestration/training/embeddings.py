"""State encoding for the LSTM Coup agent.

Turns a per-player ``private_view`` (see ``coup-api/store.py`` /
``coup-core/state_stack.py``) into fixed-size feature vectors that the LSTM
consumes. Every game snapshot becomes one timestep; the sequence of snapshots
is fed to the LSTM and the most recent snapshot is used as the "current state".

The learnable embedding tables live on this module (``FeatureEncoder``) so that
they are trained jointly with the rest of the network. Constants below are the
categorical vocabularies used both here (for context features) and by the
network's policy heads (see ``lstm.py``).
"""

import torch
import torch.nn as nn

# ---- decision types -------------------------------------------------------
ACTION = 0
RESPONSE = 1
CARD_SELECTION = 2
NO_DECISION = 3

# ---- cards (embedding vocabulary; 0 is "no card / unknown") ---------------
NO_CARD = 0
DUKE = 1
CAPTAIN = 2
ASSASSIN = 3
CONTESSA = 4
AMBASSADOR = 5

CARD_EMB_IDX = {
    "Duke": DUKE,
    "Captain": CAPTAIN,
    "Assassin": ASSASSIN,
    "Contessa": CONTESSA,
    "Ambassador": AMBASSADOR,
}
# Order of the 5-way card policy head (index -> card name).
CARD_HEAD_ORDER = ["Duke", "Captain", "Assassin", "Contessa", "Ambassador"]

# ---- actions (14-way action policy head) ----------------------------------
INCOME = 0
FOREIGN_AID = 1
TAX = 2
EXCHANGE = 3
STEAL_OPP1 = 4
STEAL_OPP2 = 5
STEAL_OPP3 = 6
ASSASSINATE_OPP1 = 7
ASSASSINATE_OPP2 = 8
ASSASSINATE_OPP3 = 9
COUP_OPP1 = 10
COUP_OPP2 = 11
COUP_OPP3 = 12
NO_ACTION = 13

NUM_ACTIONS = 14

# Non-targeted actions map to a single head slot.
UNTARGETED_ACTION_IDX = {
    "Income": INCOME,
    "Foreign Aid": FOREIGN_AID,
    "Tax": TAX,
    "Exchange": EXCHANGE,
}
# Targeted actions map to a base slot; +opponent_slot (0..2) gives the head idx.
TARGETED_ACTION_BASE = {
    "Steal": STEAL_OPP1,
    "Assassinate": ASSASSINATE_OPP1,
    "Coup": COUP_OPP1,
}

# The pending action stored in a snapshot is a *base* action (no target); this
# collapses it onto a single embedding slot for the context feature.
PENDING_ACTION_EMB_IDX = {
    None: NO_ACTION,
    "Income": INCOME,
    "Foreign Aid": FOREIGN_AID,
    "Tax": TAX,
    "Exchange": EXCHANGE,
    "Steal": STEAL_OPP1,
    "Assassinate": ASSASSINATE_OPP1,
    "Coup": COUP_OPP1,
}

# ---- responses (3-way response policy head + embedding vocabulary) --------
NO_RESPONSE = 0
PASS = 1
BLOCK = 2
CHALLENGE = 3

# Order of the 3-way response policy head (index -> response command).
RESPONSE_HEAD_ORDER = ["pass", "block", "challenge"]

# ---- phase -> decision type -----------------------------------------------
_PHASE_TO_DTYPE = {
    "AWAITING_ACTION": ACTION,
    "AWAITING_CHALLENGE": RESPONSE,
    "AWAITING_BLOCK_OR_CHALLENGE": RESPONSE,
    "AWAITING_BLOCK_CHALLENGE": RESPONSE,
    "AWAITING_CARD_SELECTION": CARD_SELECTION,
}

MAX_PLAYERS = 4
MAX_OPPONENTS = 3
MAX_COINS = 12.0
MAX_CARDS = 2.0
MAX_CARD_COPIES = 3.0  # three copies of each character exist in the deck


def phase_to_dtype(phase: str | None) -> int:
    return _PHASE_TO_DTYPE.get(phase, NO_DECISION)


def opponents_of(snapshot: dict, player_id: int) -> list[int]:
    """Live opponents of ``player_id`` in a stable order (ascending id).

    Defines the opp1/opp2/opp3 slots used by the targeted-action policy head.
    """
    return sorted(
        p["id"]
        for p in snapshot.get("players", [])
        if p["id"] != player_id and p.get("num_cards", 0) > 0
    )


class FeatureEncoder(nn.Module):
    """Encodes Coup snapshots into feature tensors.

    Layout of a single timestep vector (``feature_dim`` = 39):
      -  4  every player's coin count (self first, then opponents), coins/12
      -  3  every opponent's card count, cards/2
      -  4  decision-type embedding
      -  8  own two cards (4-d card embedding x2)
      -  5  count of each card type currently known to be in play, /3
      -  8  pending-action embedding (context)
      -  3  pending-response embedding (context)
      -  4  card-selection context (mean embedding of selectable cards)
    """

    def __init__(
        self,
        card_dim: int = 4,
        action_dim: int = 8,
        response_dim: int = 3,
        decision_dim: int = 4,
    ):
        super().__init__()
        self.card_emb = nn.Embedding(6, card_dim)
        self.action_emb = nn.Embedding(NUM_ACTIONS, action_dim)
        self.response_emb = nn.Embedding(4, response_dim)
        self.decision_emb = nn.Embedding(4, decision_dim)

        self.card_dim = card_dim
        self.feature_dim = (
            MAX_PLAYERS            # coins
            + MAX_OPPONENTS        # opponent card counts
            + decision_dim         # decision type
            + 2 * card_dim         # own cards
            + 5                    # cards in play
            + action_dim           # pending action
            + response_dim         # pending response
            + card_dim             # selection context
        )

    @property
    def device(self) -> torch.device:
        return self.decision_emb.weight.device

    def _idx(self, value: int) -> torch.Tensor:
        return torch.tensor(value, dtype=torch.long, device=self.device)

    def _card_idx(self, name) -> int:
        return CARD_EMB_IDX.get(name, NO_CARD)

    def encode_snapshot(
        self,
        snapshot: dict,
        player_id: int,
        decision_type: int | None = None,
    ) -> torch.Tensor:
        dev = self.device
        players = {p["id"]: p for p in snapshot.get("players", [])}
        opponents = opponents_of(snapshot, player_id)

        # --- coins: [self, opp1, opp2, opp3] normalised ---------------------
        ordered_ids = [player_id] + opponents
        coins = [0.0] * MAX_PLAYERS
        for slot, pid in enumerate(ordered_ids[:MAX_PLAYERS]):
            coins[slot] = players.get(pid, {}).get("num_coins", 0) / MAX_COINS
        coins_t = torch.tensor(coins, dtype=torch.float32, device=dev)

        # --- opponent card counts ------------------------------------------
        opp_cards = [0.0] * MAX_OPPONENTS
        for slot, pid in enumerate(opponents[:MAX_OPPONENTS]):
            opp_cards[slot] = players.get(pid, {}).get("num_cards", 0) / MAX_CARDS
        opp_cards_t = torch.tensor(opp_cards, dtype=torch.float32, device=dev)

        # --- decision type --------------------------------------------------
        if decision_type is None:
            decision_type = phase_to_dtype(snapshot.get("phase"))
        dtype_t = self.decision_emb(self._idx(decision_type))

        # --- own cards ------------------------------------------------------
        own = list((snapshot.get("private") or {}).get("cards", []))[:2]
        own_idx = [self._card_idx(c) for c in own]
        while len(own_idx) < 2:
            own_idx.append(NO_CARD)
        own_t = self.card_emb(
            torch.tensor(own_idx, dtype=torch.long, device=dev)
        ).reshape(-1)

        # --- cards known to be in play (own hand + discard pile) -----------
        in_play = [0.0] * 5
        for name in own + list(snapshot.get("discard_pile", [])):
            idx = self._card_idx(name)
            if idx != NO_CARD:
                in_play[idx - 1] += 1.0 / MAX_CARD_COPIES
        in_play_t = torch.tensor(in_play, dtype=torch.float32, device=dev)

        # --- pending action context ----------------------------------------
        act_idx = PENDING_ACTION_EMB_IDX.get(snapshot.get("pending_action"), NO_ACTION)
        act_t = self.action_emb(self._idx(act_idx))

        # --- pending response context --------------------------------------
        if snapshot.get("challenged"):
            resp_idx = CHALLENGE
        elif snapshot.get("blocked"):
            resp_idx = BLOCK
        elif phase_to_dtype(snapshot.get("phase")) == RESPONSE:
            resp_idx = PASS
        else:
            resp_idx = NO_RESPONSE
        resp_t = self.response_emb(self._idx(resp_idx))

        # --- card-selection context ----------------------------------------
        selection = snapshot.get("pending_selection") or {}
        sel_cards = selection.get("cards") or selection.get("candidates") or []
        sel_idx = [self._card_idx(c) for c in sel_cards]
        if sel_idx:
            sel_t = self.card_emb(
                torch.tensor(sel_idx, dtype=torch.long, device=dev)
            ).mean(dim=0)
        else:
            sel_t = self.card_emb(self._idx(NO_CARD))

        return torch.cat(
            [coins_t, opp_cards_t, dtype_t, own_t, in_play_t, act_t, resp_t, sel_t]
        )

    def encode_history(self, history: list[dict], player_id: int) -> torch.Tensor:
        """Encode every snapshot in ``history`` into a ``[T, feature_dim]`` tensor."""
        if not history:
            return torch.zeros((1, self.feature_dim), device=self.device)
        return torch.stack(
            [self.encode_snapshot(snap, player_id) for snap in history], dim=0
        )
