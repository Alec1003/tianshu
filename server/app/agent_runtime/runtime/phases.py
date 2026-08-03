from __future__ import annotations

from enum import Enum


class Phase(str, Enum):
    """Fixed request lifecycle phases for TianShu Agent Runtime."""

    PRE_DISPATCH = "pre_dispatch"
    POST_DISPATCH = "post_dispatch"
    PRE_AGENT_BUILD = "pre_agent_build"
    POST_AGENT_BUILD = "post_agent_build"
    PRE_EXECUTE = "pre_execute"
    POST_RESPONSE = "post_response"
    ON_ERROR = "on_error"
    FINALLY = "finally"


__all__ = ["Phase"]
