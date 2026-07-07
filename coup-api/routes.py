from fastapi import APIRouter, HTTPException

from action import ALL_ACTIONS
from store import STATE_STACK, RESOLVER

# Initialize the router with a standard API prefix
router = APIRouter(prefix="/api/v1", tags=["states"])


def _resolve_and_push(state, action):
    """Run the engine on a RESOLVING state (using the state's tracked response fields) and push the result."""
    state.phase = "RESOLVING"
    resolver_payload = {
        "state": state,
        "action": action,
        "blocked": state.blocked,
        "challenged": state.challenged,
        "victim_id": state.victim_id,
        "challenger_id": state.challenger_id,
        "blocker_id": state.blocker_id,
    }
    new_state = RESOLVER.generate_next_state(resolver_payload)
    STATE_STACK.add_state(new_state)
    return {"success": True, "id": new_state.turn_id, "data": new_state}


@router.get("/states")
async def get_all_states():
    """Fetch all items from the database."""
    return {"success": True, "data": STATE_STACK.get_states()}

@router.get("/states/latest")
async def get_latest_state():
    """Fetch a specific item by its unique ID."""
    return {"success": True, "data": STATE_STACK.get_states()[-1]}

@router.get("/states/private-view")
async def get_private_view(payload: dict):
    """Gets players private view"""
    return {"success": True, "data": STATE_STACK.private_view(payload)}

@router.post("/states")
async def create_state(payload: dict):
    """Create and append a new item."""
    STATE_STACK.add_state(payload)
    return {"success": True, "id": payload.get("turn_id"), "data": payload}

@router.post("/actions/resolve")
async def resolve_action(payload: dict):
    """
    Directly resolve an action against the latest state, bypassing the
    declare/respond flow below. Mainly useful for testing the engine directly.

    Expected payload: {"action": <name>, "blocked": 0|1, "challenged": 0|1,
                        "victim_id"?, "challenger_id"?, "blocker_id"?}
    """
    action_name = payload.get("action")
    if action_name not in ALL_ACTIONS:
        raise HTTPException(status_code=400, detail=f"Unknown action: {action_name}")

    state = STATE_STACK.get_states()[-1]
    state.blocked = payload.get("blocked", 0)
    state.challenged = payload.get("challenged", 0)
    if "victim_id" in payload:
        state.victim_id = payload["victim_id"]
    state.challenger_id = payload.get("challenger_id")
    state.blocker_id = payload.get("blocker_id")

    return _resolve_and_push(state, ALL_ACTIONS[action_name])

@router.post("/actions/declare")
async def declare_action(payload: dict):
    """
    The acting player declares an action. Moves the game out of AWAITING_ACTION
    into a response-collecting phase, or straight to RESOLVING if the action
    can't be blocked or challenged (e.g. Income, Coup).

    Expected payload: {"player_id": int, "action": <action name>, "target_player_id": int?}
    """
    state = STATE_STACK.get_states()[-1]

    if state.phase != "AWAITING_ACTION":
        raise HTTPException(status_code=400, detail=f"Not awaiting an action; phase is {state.phase}")

    player_id = payload.get("player_id")
    if player_id != state.acting_player_id:
        raise HTTPException(status_code=400, detail="It is not this player's turn")

    action_name = payload.get("action")
    if action_name not in ALL_ACTIONS:
        raise HTTPException(status_code=400, detail=f"Unknown action: {action_name}")
    action = ALL_ACTIONS[action_name]

    # Use the resolver's own claim tables as the source of truth for whether an
    # action can be blocked/challenged/targeted -- action.py's own flags for this
    # are out of date (e.g. Exchange is flagged has_victim, Foreign Aid is
    # flagged as having parent_cards, neither of which the resolver honors).
    blockable = action_name in RESOLVER.BLOCK_CLAIMS
    challengeable = action_name in RESOLVER.ACTION_CLAIMS
    targeted = action_name in RESOLVER.TARGETED_ACTIONS

    if targeted:
        state.victim_id = payload.get("target_player_id")

    state.pending_action = action_name
    state.blocked = 0
    state.challenged = 0
    state.challenger_id = None
    state.blocker_id = None

    if not (blockable or challengeable):
        # Nothing to block or challenge (Income, Coup) - resolve immediately.
        return _resolve_and_push(state, action)

    state.pending_responses = {
        p.id for p in state.players
        if p.id != state.acting_player_id and state.num_cards_per_player[p.id] > 0
    }
    state.phase = "AWAITING_BLOCK_OR_CHALLENGE" if blockable else "AWAITING_CHALLENGE"

    return {"success": True, "data": state}

@router.post("/actions/respond")
async def respond_to_action(payload: dict):
    """
    An opponent responds to a declared action (during AWAITING_CHALLENGE /
    AWAITING_BLOCK_OR_CHALLENGE), or the original actor responds to a
    declared block (during AWAITING_BLOCK_CHALLENGE).

    Expected payload: {"player_id": int, "response": "pass" | "challenge" | "block"}
    """
    state = STATE_STACK.get_states()[-1]

    if state.phase not in ("AWAITING_CHALLENGE", "AWAITING_BLOCK_OR_CHALLENGE", "AWAITING_BLOCK_CHALLENGE"):
        raise HTTPException(status_code=400, detail=f"Not awaiting a response; phase is {state.phase}")

    player_id = payload.get("player_id")
    response = payload.get("response")
    action = ALL_ACTIONS[state.pending_action]

    if state.phase == "AWAITING_BLOCK_CHALLENGE":
        if player_id != state.acting_player_id:
            raise HTTPException(status_code=400, detail="Only the acting player may respond to a block")
        if response == "challenge":
            state.challenged = 1
            state.challenger_id = player_id
        elif response != "pass":
            raise HTTPException(status_code=400, detail=f"Invalid response for this phase: {response}")
        return _resolve_and_push(state, action)

    if player_id not in state.pending_responses:
        raise HTTPException(status_code=400, detail="Player is not eligible to respond right now")

    if response == "challenge":
        if action.name not in RESOLVER.ACTION_CLAIMS:
            raise HTTPException(status_code=400, detail=f"{action.name} cannot be challenged")
        state.challenged = 1
        state.challenger_id = player_id
        state.pending_responses = set()
        return _resolve_and_push(state, action)

    if response == "block":
        if action.name not in RESOLVER.BLOCK_CLAIMS:
            raise HTTPException(status_code=400, detail=f"{action.name} cannot be blocked")
        state.blocked = 1
        state.victim_id = player_id
        state.blocker_id = player_id
        state.pending_responses = set()
        state.phase = "AWAITING_BLOCK_CHALLENGE"
        return {"success": True, "data": state}

    if response == "pass":
        state.pending_responses.discard(player_id)
        if not state.pending_responses:
            return _resolve_and_push(state, action)
        return {"success": True, "data": state}

    raise HTTPException(status_code=400, detail=f"Invalid response: {response}")

@router.post("/actions/select-card")
async def select_card(payload: dict):
    """
    Submit a player's choice during AWAITING_CARD_SELECTION -- either which
    card to give up for a lost influence, or which cards to keep after an
    Exchange draw. Never falls back to a random pick; the player must submit
    an explicit choice every time influence is lost or a hand is exchanged.

    Expected payload for a card loss: {"player_id": int, "card": <card name>}
    Expected payload for an exchange: {"player_id": int, "keep_cards": [<card name>, ...]}
    """
    state = STATE_STACK.get_states()[-1]

    if state.phase != "AWAITING_CARD_SELECTION":
        raise HTTPException(status_code=400, detail=f"No card selection pending; phase is {state.phase}")

    new_state = RESOLVER.apply_selection({"state": state, **payload})
    return {"success": True, "id": new_state.turn_id, "data": new_state}
