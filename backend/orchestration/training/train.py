"""Actor-critic training for the LSTM Coup agent.

Loop:
  1. Freeze the network and play ``games_per_iter`` 4-player games where the
     LSTM agent faces one easy, one medium and one hard empirical opponent.
     Every LSTM decision is recorded in the replay buffer. Rewards combine a
     terminal win/loss payoff with intermediate shaping (see ``compute_reward``)
     and are turned into discounted returns.
  2. Run a few A2C epochs over the buffer: re-encode each stored decision with
     the current parameters, and minimise
         policy_loss + value_coef * value_loss - entropy_coef * entropy
     where advantage = return - V(state).
  3. Clear the buffer and repeat. The parameters achieving the highest per-iter
     win rate so far are checkpointed to ``<save_path stem>_best.pt`` and mirrored
     to S3. Training warm-starts from the best S3 checkpoint when one exists
     (disable with ``--no-resume``).

Intermediate reward scheme (per LSTM decision, from ground-truth board deltas):
  - opponent steals coins from the LSTM : STEAL_PENALTY_PER_COIN per coin
  - any opponent loses a card           : +OPP_CARD_LOSS_REWARD per card
  - LSTM *causes* an opponent card loss  : +OPP_CARD_LOSS_CAUSED_BONUS per card
                                           (in addition to the base reward)
  - LSTM gains coins                     : +COIN_GAIN_REWARD per coin
  - LSTM loses a card                    : LSTM_CARD_LOSS_PENALTY per card

The empirical opponents replay a SQLite dataset; if it is missing locally it is
downloaded from S3 (see ``ensure_database``) before any game is played.

Run directly:  python train.py
"""

import argparse
import json
import random
import sys
from pathlib import Path

import torch
import torch.nn.functional as F
import torch.optim as optim
from torch.optim.lr_scheduler import CosineAnnealingLR

BACKEND = Path(__file__).resolve().parents[2]
for sub in ("orchestration", "coup-api", "coup-core", "agents"):
    sys.path.insert(0, str(BACKEND / sub))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from match_runner import GAME_DB, _make_agent, _next_player_id  # noqa: E402
from lstm import LSTMActorCritic, LSTMAgent, masked_categorical  # noqa: E402
from ReplayBuffer import ReplayBuffer  # noqa: E402

# ---- hyperparameters ------------------------------------------------------
num_iterations = 200
games_per_iter = 500
max_steps = 400
gamma = 0.99
hidden_size = 128
learning_rate = 3e-4
update_epochs = 4
batch_size = 128
value_coef = 0.5
entropy_coef = 0.01
grad_clip = 1.0
buffer_capacity = 40000

WIN_REWARD = 10.0
LOSS_REWARD = -10.0
DRAW_REWARD = 0.0

# Intermediate (shaping) rewards.
STEAL_PENALTY_PER_COIN = -0.25       # -0.5 for a standard 2-coin steal off the LSTM
OPP_CARD_LOSS_REWARD = 1.0           # any opponent losing a card
OPP_CARD_LOSS_CAUSED_BONUS = 1.5     # extra when the LSTM caused that loss
COIN_GAIN_REWARD = 0.1               # per coin the LSTM gains
LSTM_CARD_LOSS_PENALTY = -5.0        # per card the LSTM loses

# Coin drops of exactly these sizes are the LSTM paying for its own Coup (7) or
# Assassinate (3), not a steal, so they are never penalised.
SELF_PAY_AMOUNTS = (3, 7)

OPPONENTS = ["easy", "med", "hard"]

# Where the best checkpoint is mirrored, and where per-iteration metrics land.
S3_BUCKET = "tejas-blender-bucket"
S3_KEY = "lstm_agent_best.pt"
RESULTS_PATH = str(Path(__file__).resolve().parent / "training-results.json")

# The empirical opponents replay decisions from this SQLite dataset; if it is not
# present locally (e.g. a fresh RunPod VM) it is pulled from S3.
DB_PATH = BACKEND / "database" / "coup_generated.sqlite3"
DB_S3_BUCKET = "tejas-coup-bucket"
DB_S3_KEY = "coup_generated.sqlite3"

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")


def upload_to_s3(local_path, bucket: str, key: str) -> bool:
    """Upload ``local_path`` to ``s3://bucket/key``. Non-fatal on failure."""
    try:
        import boto3  # imported lazily so training does not require boto3

        boto3.client("s3").upload_file(str(local_path), bucket, key)
        print(f"uploaded {local_path} -> s3://{bucket}/{key}", flush=True)
        return True
    except Exception as exc:  # missing creds / network / boto3 -> keep training
        print(f"[warn] S3 upload to s3://{bucket}/{key} failed: {exc}", flush=True)
        return False


def download_from_s3(bucket: str, key: str, local_path) -> bool:
    """Download ``s3://bucket/key`` to ``local_path``. Non-fatal on failure."""
    try:
        import boto3

        Path(local_path).parent.mkdir(parents=True, exist_ok=True)
        boto3.client("s3").download_file(bucket, key, str(local_path))
        print(f"downloaded s3://{bucket}/{key} -> {local_path}", flush=True)
        return True
    except Exception as exc:  # no object / creds / network -> start fresh
        print(f"[warn] could not fetch s3://{bucket}/{key} ({exc}); starting fresh", flush=True)
        return False


def ensure_database(
    db_path=DB_PATH,
    bucket: str = DB_S3_BUCKET,
    key: str = DB_S3_KEY,
) -> None:
    """Guarantee the empirical-agent dataset exists locally, fetching it from S3.

    The empirical opponents load this SQLite file at construction, so it must be
    present before any game is played. Raises if it cannot be obtained.
    """
    db_path = Path(db_path)
    if db_path.exists():
        return

    print(f"database not found at {db_path}; fetching from s3://{bucket}/{key}", flush=True)
    if not download_from_s3(bucket, key, db_path) or not db_path.exists():
        raise RuntimeError(
            f"Could not obtain the training database. Place it at {db_path} or make "
            f"s3://{bucket}/{key} accessible (check AWS credentials)."
        )


def load_best_weights(net: LSTMActorCritic, bucket: str, key: str, local_path) -> float:
    """Fetch the best checkpoint from S3 and load it into ``net``.

    Returns the checkpoint's recorded win rate (``-inf`` if nothing was loaded),
    which seeds ``best_win_rate`` so a resumed run only overwrites the S3 copy
    when it genuinely improves.
    """
    if not download_from_s3(bucket, key, local_path):
        return float("-inf")
    try:
        ckpt = torch.load(local_path, map_location=device)
        state = ckpt["state_dict"] if isinstance(ckpt, dict) and "state_dict" in ckpt else ckpt
        net.load_state_dict(state)
        win_rate = ckpt.get("win_rate", float("-inf")) if isinstance(ckpt, dict) else float("-inf")
        print(f"resumed from S3 checkpoint (win_rate {win_rate})", flush=True)
        return win_rate
    except Exception as exc:
        print(f"[warn] failed to load checkpoint {local_path} ({exc}); starting fresh", flush=True)
        return float("-inf")


def write_results(results_path, history: list[dict], meta: dict) -> None:
    """Persist per-iteration metrics as JSON for plotting win-rate / losses."""
    payload = {"meta": meta, "history": history}
    with open(results_path, "w") as fh:
        json.dump(payload, fh, indent=2)


def _board(state) -> dict[int, tuple[int, int]]:
    """Ground-truth ``{player_id: (num_coins, num_cards)}`` for the current state."""
    return {p.id: (p.num_coins, len(p.cards)) for p in state.players}


def _aggressors(state) -> set[int]:
    """Player ids whose action/challenge/block is driving the current resolution.

    Used to decide whether the LSTM *caused* an opponent's card loss.
    """
    ids = {
        getattr(state, "acting_player_id", None),
        getattr(state, "challenger_id", None),
        getattr(state, "blocker_id", None),
    }
    ids.discard(None)
    return ids


def compute_reward(before: dict, after: dict, aggressors: set[int], lstm_pid: int) -> float:
    """Intermediate reward from one dispatch, seen from the LSTM's perspective."""
    reward = 0.0

    before_coins, before_cards = before.get(lstm_pid, (0, 0))
    after_coins, after_cards = after.get(lstm_pid, (0, 0))

    coin_delta = after_coins - before_coins
    if coin_delta > 0:
        reward += COIN_GAIN_REWARD * coin_delta
    elif coin_delta < 0:
        loss = -coin_delta
        if loss not in SELF_PAY_AMOUNTS:  # otherwise it is a Coup/Assassinate payment
            reward += STEAL_PENALTY_PER_COIN * loss

    lstm_caused = lstm_pid in aggressors
    for pid, (b_coins, b_cards) in before.items():
        _, a_cards = after.get(pid, (0, b_cards))
        lost = b_cards - a_cards
        if lost <= 0:
            continue
        if pid == lstm_pid:
            reward += LSTM_CARD_LOSS_PENALTY * lost
        else:
            reward += OPP_CARD_LOSS_REWARD * lost
            if lstm_caused:
                reward += OPP_CARD_LOSS_CAUSED_BONUS * lost

    return reward


def play_game(game_id: str, lstm_agent: LSTMAgent, opponent_names: list[str]) -> tuple[int | None, int]:
    """Play one 4-player game; returns ``(winner_player_id_or_None, lstm_player_id)``."""
    lstm_pid = random.randint(1, 4)
    seats = [None, None, None, None]
    seats[lstm_pid - 1] = "lstm"
    others = list(opponent_names)
    random.shuffle(others)
    it = iter(others)
    for i in range(4):
        if seats[i] is None:
            seats[i] = next(it)

    player_agents = {i + 1: name for i, name in enumerate(seats)}
    GAME_DB.create_game(game_id=game_id, num_players=4, player_agents=player_agents)

    agents = {}
    for pid, name in player_agents.items():
        agents[pid] = lstm_agent if name == "lstm" else _make_agent(name)

    lstm_agent.reset_episode()

    # Index in lstm_agent.memory of the LSTM's most recent decision; intermediate
    # rewards observed after it are credited to that decision.
    last_idx: int | None = None

    for _ in range(max_steps):
        state = GAME_DB.latest_state(game_id)
        if state.phase == "GAME_OVER":
            break
        pid = _next_player_id(state)
        if pid is None:
            break

        before = _board(state)
        aggressors = _aggressors(state)
        mem_before = len(lstm_agent.memory)

        private_view = GAME_DB.private_view(game_id, pid)
        try:
            result = agents[pid].decide(private_view, data_generation=True)
            GAME_DB.dispatch_decision(game_id, pid, result["decision"])
        except Exception:
            break

        # A decision by the LSTM becomes the new credit target so that the
        # immediate effect of its own move (e.g. coins gained) lands on it.
        if pid == lstm_pid and len(lstm_agent.memory) > mem_before:
            last_idx = len(lstm_agent.memory) - 1

        after = _board(GAME_DB.latest_state(game_id))
        reward = compute_reward(before, after, aggressors, lstm_pid)
        if last_idx is not None and reward != 0.0:
            step = lstm_agent.memory[last_idx]
            step["reward"] = step.get("reward", 0.0) + reward

    summary = GAME_DB.game_summary(game_id)
    winner = summary.get("winner_id")
    return winner, lstm_pid


def collect(buffer: ReplayBuffer, net: LSTMActorCritic, iteration: int) -> float:
    """Play a batch of games, fill the buffer, return the LSTM win rate."""
    net.eval()
    agent = LSTMAgent(net, device=device, deterministic=False, record=True)
    wins = 0
    for g in range(games_per_iter):
        game_id = f"train-{iteration}-{g}"
        winner, lstm_pid = play_game(game_id, agent, OPPONENTS)
        if winner == lstm_pid:
            reward = WIN_REWARD
            wins += 1
        elif winner is None:
            reward = DRAW_REWARD
        else:
            reward = LOSS_REWARD
        buffer.add_episode(agent.memory, reward, gamma=gamma)
    return wins / games_per_iter


def update(buffer: ReplayBuffer, net: LSTMActorCritic, optimizer) -> dict:
    net.train()
    stats = {"policy_loss": 0.0, "value_loss": 0.0, "entropy": 0.0, "batches": 0}

    for _ in range(update_epochs):
        for groups in buffer.epochs(batch_size):
            optimizer.zero_grad()
            total_loss = torch.zeros((), device=device)
            n_steps = 0
            policy_acc = value_acc = entropy_acc = 0.0

            for head, steps in groups.items():
                batch = ReplayBuffer.collate(steps, net.encoder, device)
                logits, value = net(batch["seq"], batch["lengths"], batch["curr"], head)
                dist = masked_categorical(logits, batch["mask"])

                log_prob = dist.log_prob(batch["action_idx"])
                entropy = dist.entropy().mean()
                advantage = (batch["ret"] - value).detach()

                policy_loss = -(advantage * log_prob).mean()
                value_loss = F.mse_loss(value, batch["ret"])

                weight = len(steps)
                total_loss = total_loss + weight * (
                    policy_loss + value_coef * value_loss - entropy_coef * entropy
                )
                n_steps += weight
                policy_acc += policy_loss.item() * weight
                value_acc += value_loss.item() * weight
                entropy_acc += entropy.item() * weight

            if n_steps == 0:
                continue
            (total_loss / n_steps).backward()
            torch.nn.utils.clip_grad_norm_(net.parameters(), grad_clip)
            optimizer.step()

            stats["policy_loss"] += policy_acc / n_steps
            stats["value_loss"] += value_acc / n_steps
            stats["entropy"] += entropy_acc / n_steps
            stats["batches"] += 1

    if stats["batches"]:
        for key in ("policy_loss", "value_loss", "entropy"):
            stats[key] /= stats["batches"]
    return stats


def train(
    iterations: int = num_iterations,
    save_path: str | None = None,
    results_path: str | None = RESULTS_PATH,
    s3_bucket: str | None = S3_BUCKET,
    s3_key: str = S3_KEY,
    resume: bool = True,
) -> LSTMActorCritic:
    ensure_database()

    net = LSTMActorCritic(hidden_size=hidden_size).to(device)
    optimizer = optim.Adam(net.parameters(), lr=learning_rate)
    scheduler = CosineAnnealingLR(optimizer, T_max=max(iterations, 1))
    buffer = ReplayBuffer(capacity=buffer_capacity)

    best_path = None
    if save_path:
        save_path = Path(save_path)
        save_path.parent.mkdir(parents=True, exist_ok=True)
        best_path = save_path.with_name(f"{save_path.stem}_best{save_path.suffix}")
    best_win_rate = float("-inf")

    # Warm-start from the best checkpoint stored in S3 (if any).
    if resume and s3_bucket:
        resume_path = best_path or (Path(__file__).resolve().parent / S3_KEY)
        best_win_rate = load_best_weights(net, s3_bucket, s3_key, resume_path)

    history: list[dict] = []
    meta = {
        "opponents": OPPONENTS,
        "games_per_iter": games_per_iter,
        "gamma": gamma,
        "hidden_size": hidden_size,
        "learning_rate": learning_rate,
        "metrics": ["win_rate", "policy_loss", "value_loss", "entropy", "lr"],
    }

    for iteration in range(iterations):
        win_rate = collect(buffer, net, iteration)
        stats = update(buffer, net, optimizer)
        buffer.clear()
        scheduler.step()

        is_best = win_rate > best_win_rate
        if is_best:
            best_win_rate = win_rate

        print(
            f"iter {iteration:03d} | win_rate {win_rate:5.2f} | "
            f"policy {stats['policy_loss']:+.4f} | value {stats['value_loss']:.4f} | "
            f"entropy {stats['entropy']:.4f} | lr {scheduler.get_last_lr()[0]:.2e}"
            f"{'  <- best' if is_best else ''}",
            flush=True,
        )

        history.append(
            {
                "iteration": iteration,
                "win_rate": win_rate,
                "policy_loss": stats["policy_loss"],
                "value_loss": stats["value_loss"],
                "entropy": stats["entropy"],
                "lr": scheduler.get_last_lr()[0],
                "is_best": is_best,
            }
        )
        if results_path:
            write_results(results_path, history, {**meta, "best_win_rate": best_win_rate})

        if best_path and is_best:
            torch.save(
                {"state_dict": net.state_dict(), "win_rate": win_rate, "iteration": iteration},
                best_path,
            )
            if s3_bucket:
                upload_to_s3(best_path, s3_bucket, s3_key)
        if save_path and (iteration + 1) % 10 == 0:
            torch.save(net.state_dict(), save_path)

    if save_path:
        torch.save(net.state_dict(), save_path)
    if best_path:
        print(f"best win_rate {best_win_rate:.2f} saved to {best_path}", flush=True)
    if results_path:
        print(f"training results written to {results_path}", flush=True)
    return net


def main() -> None:
    global games_per_iter
    parser = argparse.ArgumentParser(description="Train the LSTM Coup agent with A2C.")
    parser.add_argument("--iterations", type=int, default=num_iterations)
    parser.add_argument("--games-per-iter", type=int, default=games_per_iter)
    parser.add_argument("--save-path", default=str(Path(__file__).resolve().parent / "lstm_agent.pt"))
    parser.add_argument("--results-path", default=RESULTS_PATH)
    parser.add_argument("--s3-bucket", default=S3_BUCKET, help="Set to '' to disable S3 sync.")
    parser.add_argument("--s3-key", default=S3_KEY)
    parser.add_argument(
        "--no-resume",
        dest="resume",
        action="store_false",
        help="Ignore any existing S3 checkpoint and train from scratch.",
    )
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()

    games_per_iter = args.games_per_iter
    random.seed(args.seed)
    torch.manual_seed(args.seed)

    print(f"device: {device}", flush=True)
    train(
        iterations=args.iterations,
        save_path=args.save_path,
        results_path=args.results_path,
        s3_bucket=args.s3_bucket or None,
        s3_key=args.s3_key,
        resume=args.resume,
    )


if __name__ == "__main__":
    main()
