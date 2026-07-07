from fastapi import APIRouter, HTTPException

from action import ALL_ACTIONS
from store import STATE_STACK, RESOLVER

# Initialize the router with a standard API prefix
router = APIRouter(prefix="/api/v1", tags=["states"])


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
    Take an action submitted by a client, resolve it against the latest state
    via the game engine (resolver.py), and push the resulting state onto the stack.

    Expected payload: {"action": <action name>, "blocked": 0|1, "challenged": 0|1}
    """
    action_name = payload.get("action")
    if action_name not in ALL_ACTIONS:
        raise HTTPException(status_code=400, detail=f"Unknown action: {action_name}")

    state = STATE_STACK.get_states()[-1]
    resolver_payload = {
        "state": state,
        "action": ALL_ACTIONS[action_name],
        "blocked": payload.get("blocked", 0),
        "challenged": payload.get("challenged", 0),
    }

    new_state = RESOLVER.generate_next_state(resolver_payload)
    STATE_STACK.add_state(new_state)

    return {"success": True, "id": new_state.turn_id, "data": new_state}
