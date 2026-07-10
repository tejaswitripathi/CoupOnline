from typing import Optional

from pydantic import BaseModel, Field


class GameCreateRequest(BaseModel):
    game_id: Optional[str] = None
    num_players: int = Field(default=4, ge=2, le=4)
    player_agents: dict[int, str] = Field(default_factory=dict)


class GameScopedRequest(BaseModel):
    game_id: Optional[str] = None


class PrivateViewRequest(GameScopedRequest):
    player_id: int


class ResolveActionRequest(GameScopedRequest):
    action: str
    blocked: int = 0
    challenged: int = 0
    victim_id: Optional[int] = None
    challenger_id: Optional[int] = None
    blocker_id: Optional[int] = None


class DeclareActionRequest(GameScopedRequest):
    player_id: int
    action: str
    target_player_id: Optional[int] = None


class RespondRequest(GameScopedRequest):
    player_id: int
    response: str


class SelectCardRequest(GameScopedRequest):
    player_id: int
    card: Optional[str] = None
    keep_cards: Optional[list[str]] = None


class AgentDecisionRequest(GameScopedRequest):
    player_id: int
    include_private_view: bool = False
    data_generation: bool = True


class MatchRunRequest(BaseModel):
    game_id: Optional[str] = None
    num_players: int = Field(default=4, ge=2, le=4)
    player_agents: dict[int, str] = Field(default_factory=dict)
    max_steps: int = Field(default=200, ge=1)
    include_private_view: bool = False
