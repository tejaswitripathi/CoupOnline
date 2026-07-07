from fastapi import APIRouter, HTTPException

from coup-core.state import State, StateStack
from coup-core.player import Player

# Initialize the router with a standard API prefix
router = APIRouter(prefix="/api/v1", tags=["states"])



@router.get("/states")
async def get_all_states():
    """Fetch all items from the database."""
    return {"success": True, "data": STATE_STACK.get_states()}

@router.get("/states/latest")
async def get_latest_state():
    """Fetch a specific item by its unique ID."""
    # if item_id not in ITEMS_DB:
    #     raise HTTPException(status_code=404, detail="Item not found")
    return {"success": True, "data": STATE_STACK.get_states()[-1]}

@router.post("/states")
async def create_state(payload: State):
    """Create and append a new item."""
    # new_id = max(ITEMS_DB.keys()) + 1
    # ITEMS_DB[new_id] = payload
    STATE_STACK.add_state(payload)
    return {"success": True, "id": payload.turn_id, "data": payload}