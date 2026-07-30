"""LSTM actor-critic agent for Coup.

The network reads the whole game so far as a sequence (one timestep per game
snapshot), feeds it through an LSTM, concatenates the LSTM summary with an
encoding of the current decision point, and passes that through a shared MLP.
Three policy heads (action / response / card-selection) plus a value head sit
on top of the shared trunk, so the same body serves the actor and the critic.

Current state layout for each timestep (see ``embeddings.FeatureEncoder``):
- every player's coin count            -> 4
- every other player's card count      -> 3
- decision type (4-d embedding)        -> 4
- LSTM player's cards (4-d emb x 2)     -> 8
- number of each card in play          -> 5
- pending action (8-d embedding)        -> 8
- pending response (3-d embedding)      -> 3
- card-selection context (4-d)          -> 4

``LSTMActorCritic`` is the trainable module. ``LSTMAgent`` wraps it with the
``decide(private_view, ...)`` interface used by the match runner and records
the trajectory (state / decision-type / legal mask / chosen index) so the
training loop can assign rewards and update the parameters afterwards.
"""

import sys
from pathlib import Path

import torch
import torch.nn as nn
import torch.nn.functional as F

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "orchestration" / "training"))

from embeddings import (  # noqa: E402
    ACTION,
    RESPONSE,
    CARD_SELECTION,
    CARD_HEAD_ORDER,
    RESPONSE_HEAD_ORDER,
    NUM_ACTIONS,
    UNTARGETED_ACTION_IDX,
    TARGETED_ACTION_BASE,
    FeatureEncoder,
    opponents_of,
)

# String keys used to select a policy head.
HEAD_ACTION = "action"
HEAD_RESPONSE = "response"
HEAD_CARD = "card"

HEAD_SIZES = {HEAD_ACTION: NUM_ACTIONS, HEAD_RESPONSE: 3, HEAD_CARD: 5}


def masked_categorical(logits: torch.Tensor, mask: torch.Tensor) -> torch.distributions.Categorical:
    """Categorical over ``logits`` with illegal entries (mask == False) removed."""
    neg_inf = torch.finfo(logits.dtype).min
    masked = logits.masked_fill(~mask, neg_inf)
    return torch.distributions.Categorical(logits=masked)


class LSTMActorCritic(nn.Module):
    def __init__(self, hidden_size: int = 128, encoder: FeatureEncoder | None = None):
        super().__init__()
        self.encoder = encoder or FeatureEncoder()
        self.hidden_size = hidden_size
        feat = self.encoder.feature_dim

        self.lstm = nn.LSTM(feat, hidden_size, batch_first=True)
        self.curr_state_encoder = nn.Sequential(
            nn.Linear(feat, hidden_size),
            nn.ReLU(),
        )
        self.shared_mlp = nn.Sequential(
            nn.Linear(2 * hidden_size, hidden_size),
            nn.ReLU(),
            nn.Linear(hidden_size, hidden_size),
            nn.ReLU(),
            nn.Linear(hidden_size, hidden_size),
            nn.ReLU(),
        )

        self.heads = nn.ModuleDict(
            {
                HEAD_ACTION: nn.Linear(hidden_size, HEAD_SIZES[HEAD_ACTION]),
                HEAD_RESPONSE: nn.Linear(hidden_size, HEAD_SIZES[HEAD_RESPONSE]),
                HEAD_CARD: nn.Linear(hidden_size, HEAD_SIZES[HEAD_CARD]),
            }
        )
        self.value_head = nn.Linear(hidden_size, 1)

    def trunk(self, seq: torch.Tensor, lengths: torch.Tensor, curr: torch.Tensor) -> torch.Tensor:
        """Shared representation for a padded batch of sequences.

        ``seq``    : [B, T, feat] (right-padded with zeros)
        ``lengths``: [B] valid length of each sequence
        ``curr``   : [B, feat] current-decision features
        """
        out, _ = self.lstm(seq)
        lengths = lengths.to(out.device).long().clamp(min=1)
        idx = (lengths - 1).view(-1, 1, 1).expand(-1, 1, out.size(2))
        h_last = out.gather(1, idx).squeeze(1)
        curr_enc = self.curr_state_encoder(curr)
        return self.shared_mlp(torch.cat([h_last, curr_enc], dim=1))

    def forward(
        self,
        seq: torch.Tensor,
        lengths: torch.Tensor,
        curr: torch.Tensor,
        head: str,
    ) -> tuple[torch.Tensor, torch.Tensor]:
        shared = self.trunk(seq, lengths, curr)
        logits = self.heads[head](shared)
        value = self.value_head(shared).squeeze(-1)
        return logits, value


class LSTMAgent:
    """Match-runner compatible wrapper around ``LSTMActorCritic``.

    Set ``record=True`` (default) during training so each decision is stored in
    ``self.memory`` as a transition dict the replay buffer can consume:
        {"history", "player_id", "head", "mask", "action_idx"}
    Rewards are terminal (assigned by the training loop), so no per-step reward
    is stored here.
    """

    provider = "local"
    model = "lstm"

    def __init__(self, net: LSTMActorCritic, device=None, deterministic: bool = False, record: bool = True):
        self.net = net
        self.device = device or next(net.parameters()).device
        self.deterministic = deterministic
        self.record = record
        self.memory: list[dict] = []

    def reset_episode(self) -> None:
        self.memory = []

    # ---- main entry point --------------------------------------------------

    def decide(self, private_view: dict, data_generation: bool = True) -> dict:
        legal_next = private_view.get("legal_next", {})
        selection = legal_next.get("selection")

        # Exchange keep-selection keeps a subset of cards; it is decomposed into
        # a sequence of single-card picks through the same card head.
        if selection and selection.get("kind") == "exchange":
            return self._decide_exchange(private_view, selection)

        history = private_view["history"]
        player_id = private_view["player_id"]
        snapshot = history[-1]

        head, mask, decode_info = self._classify(legal_next, snapshot, player_id)

        seq = self.net.encoder.encode_history(history, player_id)
        curr = seq[-1]
        mask_t = torch.tensor(mask, dtype=torch.bool, device=self.device)
        lengths = torch.tensor([seq.size(0)], device=self.device)

        self.net.eval()
        with torch.no_grad():
            logits, _ = self.net(
                seq.unsqueeze(0).to(self.device),
                lengths,
                curr.unsqueeze(0).to(self.device),
                head,
            )
            dist = masked_categorical(logits, mask_t.unsqueeze(0))
            action_idx = int(dist.probs.argmax(dim=-1)) if self.deterministic else int(dist.sample())

        decision = self._decode(head, action_idx, decode_info)

        if self.record:
            self.memory.append(
                {
                    "history": history,
                    "player_id": player_id,
                    "head": head,
                    "mask": mask,
                    "action_idx": action_idx,
                }
            )
        return self._result(decision, trainable=True)

    # ---- decision classification & legal masks -----------------------------

    def _classify(self, legal_next: dict, snapshot: dict, player_id: int):
        declarations = legal_next.get("declarations") or []
        responses = legal_next.get("responses") or []
        selection = legal_next.get("selection")

        if declarations:
            return HEAD_ACTION, *self._action_mask(declarations, snapshot, player_id)
        if responses:
            return HEAD_RESPONSE, *self._response_mask(responses)
        if selection and selection.get("kind") == "lose_influence":
            return HEAD_CARD, *self._card_mask(selection.get("cards", []))
        # Fallback: nothing actionable (should not happen on our turn).
        return HEAD_ACTION, [False] * NUM_ACTIONS, {"kind": "noop"}

    def _action_mask(self, declarations: list[dict], snapshot: dict, player_id: int):
        mask = [False] * NUM_ACTIONS
        opponents = opponents_of(snapshot, player_id)
        opp_slot = {pid: slot for slot, pid in enumerate(opponents)}
        # head_idx -> (action_name, target_player_id or None)
        decode: dict[int, tuple] = {}

        for decl in declarations:
            name = decl["action"]
            if name in UNTARGETED_ACTION_IDX:
                idx = UNTARGETED_ACTION_IDX[name]
                mask[idx] = True
                decode[idx] = (name, None)
            elif name in TARGETED_ACTION_BASE:
                base = TARGETED_ACTION_BASE[name]
                for tid in decl.get("valid_target_ids", []):
                    slot = opp_slot.get(tid)
                    if slot is None or slot >= 3:
                        continue
                    idx = base + slot
                    mask[idx] = True
                    decode[idx] = (name, tid)
        return mask, {"kind": "declare", "decode": decode}

    def _response_mask(self, responses: list[str]):
        mask = [name in responses for name in RESPONSE_HEAD_ORDER]
        return mask, {"kind": "respond"}

    def _card_mask(self, cards: list[str]):
        available = set(cards)
        mask = [name in available for name in CARD_HEAD_ORDER]
        return mask, {"kind": "lose_influence"}

    # ---- decode a sampled head index into a game decision -------------------

    def _decode(self, head: str, action_idx: int, info: dict) -> dict:
        kind = info.get("kind")
        if kind == "declare":
            name, target = info["decode"][action_idx]
            decision = {"command": "declare", "action": name}
            if target is not None:
                decision["target_player_id"] = target
            return decision
        if kind == "respond":
            return {"command": "respond", "response": RESPONSE_HEAD_ORDER[action_idx]}
        if kind == "lose_influence":
            return {"command": "select_card", "card": CARD_HEAD_ORDER[action_idx]}
        return {"command": "noop"}

    # ---- exchange keep-selection (trained via the card head) ----------------

    def _decide_exchange(self, private_view: dict, selection: dict) -> dict:
        """Choose which cards to keep after an Exchange.

        Keeping a subset of size ``keep_count`` is decomposed into that many
        sequential single-card picks. Each pick is an ordinary ``card`` decision
        (5-way head, masked to card types still available among the remaining
        candidates), so it flows through the replay buffer exactly like a
        ``lose_influence`` selection. The LSTM trunk output is identical across
        the sub-picks (the game state does not advance between them), so we run
        the network once and only re-mask/re-sample per pick.
        """
        history = private_view["history"]
        player_id = private_view["player_id"]

        candidates = list(selection.get("candidates") or [])
        keep_count = selection.get("keep_count", 0)

        seq = self.net.encoder.encode_history(history, player_id)
        curr = seq[-1]
        lengths = torch.tensor([seq.size(0)], device=self.device)

        self.net.eval()
        with torch.no_grad():
            logits, _ = self.net(
                seq.unsqueeze(0).to(self.device),
                lengths,
                curr.unsqueeze(0).to(self.device),
                HEAD_CARD,
            )

        remaining = list(candidates)
        kept: list[str] = []
        for _ in range(keep_count):
            mask = [name in remaining for name in CARD_HEAD_ORDER]
            if not any(mask):
                break
            mask_t = torch.tensor(mask, dtype=torch.bool, device=self.device)
            dist = masked_categorical(logits, mask_t.unsqueeze(0))
            action_idx = int(dist.probs.argmax(dim=-1)) if self.deterministic else int(dist.sample())

            card_name = CARD_HEAD_ORDER[action_idx]
            kept.append(card_name)
            remaining.remove(card_name)

            if self.record:
                self.memory.append(
                    {
                        "history": history,
                        "player_id": player_id,
                        "head": HEAD_CARD,
                        "mask": mask,
                        "action_idx": action_idx,
                    }
                )

        return self._result({"command": "select_card", "keep_cards": kept}, trainable=True)

    # ---- output shaping ----------------------------------------------------

    def _result(self, decision: dict, trainable: bool) -> dict:
        return {
            "provider": self.provider,
            "model": self.model,
            "decision": decision,
            "raw_output": decision,
            "trainable": trainable,
        }
