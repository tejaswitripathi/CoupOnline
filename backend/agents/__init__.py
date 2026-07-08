from .gpt_agent import GPTAgent
from .gemini_agent import GeminiAgent
from .claude_agent import ClaudeAgent


AGENTS = {
    "gpt": GPTAgent,
    "openai": GPTAgent,
    "gemini": GeminiAgent,
    "claude": ClaudeAgent,
    "anthropic": ClaudeAgent,
}
