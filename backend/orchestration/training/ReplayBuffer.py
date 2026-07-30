"""Trajectory buffer for the LSTM actor-critic training loop.

Play is on-policy: with the parameters frozen, the LSTM agent plays a batch of
games and each of its decisions is recorded as a transition. Rewards are
terminal (win / loss), so ``add_episode`` back-fills a discounted
Monte-Carlo return for every step. The buffer then serves minibatches, grouped
by decision-type head, that the update step re-encodes with the *current*
parameters (so the embeddings and LSTM receive gradients).

A stored step is a dict:
    {"history", "player_id", "head", "mask", "action_idx", "ret"}
"""

import random
from collections import defaultdict

import torch


class ReplayBuffer:
    def __init__(self, capacity: int = 20000):
        self.capacity = capacity
        self.buffer: list[dict] = []

    def __len__(self) -> int:
        return len(self.buffer)

    def clear(self) -> None:
        self.buffer = []

    # ---- ingestion ---------------------------------------------------------

    def push(self, step: dict) -> None:
        self.buffer.append(step)
        if len(self.buffer) > self.capacity:
            self.buffer.pop(0)

    def add_episode(self, steps: list[dict], final_reward: float, gamma: float = 0.99) -> None:
        """Assign discounted returns to a finished episode and store its steps.

        ``steps`` is the ordered list of transitions recorded by ``LSTMAgent``
        during one game; ``final_reward`` is the terminal reward for that game
        (e.g. +1 win, -1 loss).
        """
        running = float(final_reward)
        returns = []
        for step in reversed(steps):
            running = float(step.get("reward", 0.0)) + gamma * running
            returns.append(running)
        returns.reverse()

        for step, ret in zip(steps, returns):
            stored = {
                "history": step["history"],
                "player_id": step["player_id"],
                "head": step["head"],
                "mask": step["mask"],
                "action_idx": step["action_idx"],
                "ret": ret,
            }
            self.push(stored)

    # ---- sampling ----------------------------------------------------------

    def epochs(self, batch_size: int):
        """Yield ``{head: [steps]}`` minibatches covering the whole buffer once."""
        data = list(self.buffer)
        random.shuffle(data)
        for start in range(0, len(data), batch_size):
            chunk = data[start : start + batch_size]
            groups: dict[str, list[dict]] = defaultdict(list)
            for step in chunk:
                groups[step["head"]].append(step)
            yield groups

    def sample(self, batch_size: int) -> list[dict]:
        return random.sample(self.buffer, min(batch_size, len(self.buffer)))

    # ---- collation ---------------------------------------------------------

    @staticmethod
    def collate(steps: list[dict], encoder, device) -> dict:
        """Re-encode a group of same-head steps into padded training tensors.

        Re-encoding here (rather than reusing cached features) is what lets the
        encoder's embeddings receive gradients during the update.
        """
        seqs = [encoder.encode_history(s["history"], s["player_id"]) for s in steps]
        lengths = [seq.size(0) for seq in seqs]
        batch = len(seqs)
        t_max = max(lengths)
        feat = encoder.feature_dim

        padded = torch.zeros((batch, t_max, feat), device=device)
        curr = torch.zeros((batch, feat), device=device)
        for i, seq in enumerate(seqs):
            seq = seq.to(device)
            padded[i, : lengths[i]] = seq
            curr[i] = seq[lengths[i] - 1]

        masks = torch.tensor([s["mask"] for s in steps], dtype=torch.bool, device=device)
        actions = torch.tensor([s["action_idx"] for s in steps], dtype=torch.long, device=device)
        rets = torch.tensor([s["ret"] for s in steps], dtype=torch.float32, device=device)
        lengths_t = torch.tensor(lengths, dtype=torch.long, device=device)

        return {
            "seq": padded,
            "lengths": lengths_t,
            "curr": curr,
            "mask": masks,
            "action_idx": actions,
            "ret": rets,
        }
