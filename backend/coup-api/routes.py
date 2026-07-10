import sys
from pathlib import Path

from fastapi import APIRouter, HTTPException

from store import DEFAULT_GAME_ID, GAME_DB
from schemas import (
    AgentDecisionRequest,
    DeclareActionRequest,
    GameCreateRequest,
    MatchRunRequest,
    PrivateViewRequest,
    ResolveActionRequest,
    RespondRequest,
    SelectCardRequest,
)

AGENTS_DIR = Path(__file__).resolve().parent.parent / "agents"
ORCHESTRATION_DIR = Path(__file__).resolve().parent.parent / "orchestration"
for path in (AGENTS_DIR, ORCHESTRATION_DIR):
    sys.path.insert(0, str(path))

from base import AgentAPIError
from claude_agent import ClaudeAgent
from gemini_agent import GeminiAgent
from gpt_agent import GPTAgent
from match_runner import RandomAgent


router = APIRouter(prefix="/api/v1", tags=["states"])

AGENT_CLASSES = {
    "gpt": GPTAgent,
    "openai": GPTAgent,
    "gemini": GeminiAgent,
    "claude": ClaudeAgent,
    "anthropic": ClaudeAgent,
    "random": RandomAgent,
}


def _model_dict(model) -> dict:
    if hasattr(model, "model_dump"):
        return model.model_dump(exclude_none=True)
    return model.dict(exclude_none=True)


def _http_assert(callable_):
    try:
        return callable_()
    except AssertionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _get_agent(agent_name: str):
    agent_cls = AGENT_CLASSES.get(agent_name)
    if not agent_cls:
        raise HTTPException(status_code=404, detail=f"Unknown agent: {agent_name}")
    try:
        return agent_cls()
    except AgentAPIError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


def _agent_decision(
    agent_name: str,
    game_id: str | None,
    player_id: int,
    data_generation: bool = True,
) -> dict:
    private_view = _http_assert(lambda: GAME_DB.private_view(game_id, player_id))
    agent = _get_agent(agent_name)
    try:
        return agent.decide(private_view, data_generation=data_generation)
    except AgentAPIError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/games")
async def list_games():
    return {"success": True, "data": GAME_DB.list_games()}


@router.post("/games")
async def create_game(payload: GameCreateRequest):
    data = _model_dict(payload)
    record = _http_assert(
        lambda: GAME_DB.create_game(
            game_id=data.get("game_id"),
            num_players=data.get("num_players", 4),
            player_agents=data.get("player_agents", {}),
        )
    )
    return {"success": True, "data": GAME_DB.game_summary(record.id)}


@router.get("/games/{game_id}")
async def get_game(game_id: str):
    return {"success": True, "data": _http_assert(lambda: GAME_DB.game_summary(game_id))}


@router.get("/states")
async def get_all_states(game_id: str = DEFAULT_GAME_ID):
    record = _http_assert(lambda: GAME_DB.get_game(game_id))
    return {"success": True, "data": record.state_stack.get_states()}


@router.get("/states/latest")
async def get_latest_state(game_id: str = DEFAULT_GAME_ID):
    return {"success": True, "data": _http_assert(lambda: GAME_DB.latest_state(game_id))}


@router.get("/states/private-view")
async def get_private_view(player_id: int, game_id: str = DEFAULT_GAME_ID):
    return {"success": True, "data": _http_assert(lambda: GAME_DB.private_view(game_id, player_id))}


@router.get("/states/private-view/{player_id}")
async def get_private_view_by_path(player_id: int, game_id: str = DEFAULT_GAME_ID):
    return {"success": True, "data": _http_assert(lambda: GAME_DB.private_view(game_id, player_id))}


@router.get("/states/observation")
async def get_observation(game_id: str = DEFAULT_GAME_ID, reveal: bool = False):
    return {"success": True, "data": _http_assert(lambda: GAME_DB.observation(game_id, reveal))}


@router.post("/states/private-view")
async def post_private_view(payload: PrivateViewRequest):
    data = _model_dict(payload)
    return {
        "success": True,
        "data": _http_assert(lambda: GAME_DB.private_view(data.get("game_id"), data["player_id"])),
    }


@router.post("/actions/resolve")
async def resolve_action(payload: ResolveActionRequest):
    data = _model_dict(payload)
    game_id = data.pop("game_id", None)
    state = _http_assert(lambda: GAME_DB.resolve_action(game_id, data))
    return {"success": True, "id": state.turn_id, "data": state}


@router.post("/actions/declare")
async def declare_action(payload: DeclareActionRequest):
    data = _model_dict(payload)
    game_id = data.pop("game_id", None)
    state = _http_assert(lambda: GAME_DB.declare_action(game_id, data))
    return {"success": True, "id": state.turn_id, "data": state}


@router.post("/actions/respond")
async def respond_to_action(payload: RespondRequest):
    data = _model_dict(payload)
    game_id = data.pop("game_id", None)
    state = _http_assert(lambda: GAME_DB.respond_to_action(game_id, data))
    return {"success": True, "id": state.turn_id, "data": state}


@router.post("/actions/select-card")
async def select_card(payload: SelectCardRequest):
    data = _model_dict(payload)
    game_id = data.pop("game_id", None)
    state = _http_assert(lambda: GAME_DB.select_card(game_id, data))
    return {"success": True, "id": state.turn_id, "data": state}


@router.get("/agents")
async def list_agents():
    return {
        "success": True,
        "data": {
            "gpt": {"provider": "openai", "model": GPTAgent.model},
            "gemini": {
                "provider": "gemini",
                "model": GeminiAgent.model,
                "thinking_level": "high",
            },
            "claude": {"provider": "anthropic", "model": ClaudeAgent.model},
            "random": {"provider": "local", "model": RandomAgent.model},
        },
    }


@router.post("/agents/{agent_name}/decision")
async def agent_decision(agent_name: str, payload: AgentDecisionRequest):
    data = _model_dict(payload)
    private_view = _http_assert(lambda: GAME_DB.private_view(data.get("game_id"), data["player_id"]))
    result = _agent_decision(
        agent_name,
        data.get("game_id"),
        data["player_id"],
        data_generation=data.get("data_generation", True),
    )
    if data.get("include_private_view", False):
        result["private_view"] = private_view
    return {"success": True, "data": result}


@router.post("/agents/{agent_name}/act")
async def agent_act(agent_name: str, payload: AgentDecisionRequest):
    data = _model_dict(payload)
    game_id = data.get("game_id")
    private_view = _http_assert(lambda: GAME_DB.private_view(game_id, data["player_id"]))
    result = _agent_decision(
        agent_name,
        game_id,
        data["player_id"],
        data_generation=data.get("data_generation", True),
    )
    state = _http_assert(lambda: GAME_DB.dispatch_decision(game_id, data["player_id"], result["decision"]))
    if data.get("include_private_view", False):
        result["private_view"] = private_view

    return {
        "success": True,
        "data": {
            "agent": result,
            "state": state,
            "game": GAME_DB.game_summary(game_id),
        },
    }


@router.post("/matches/run")
async def run_match(payload: MatchRunRequest):
    from match_runner import run_match as run_observed_match

    data = _model_dict(payload)
    return {
        "success": True,
        "data": _http_assert(
            lambda: run_observed_match(
                game_id=data.get("game_id"),
                num_players=data.get("num_players", 4),
                player_agents=data.get("player_agents", {}),
                max_steps=data.get("max_steps", 200),
                include_private_view=data.get("include_private_view", False),
            )
        ),
    }
