"""Built-in subagent configurations."""

from .bash_agent import BASH_AGENT_CONFIG
from .game_designer import GAME_DESIGN_CONFIG
from .general_purpose import GENERAL_PURPOSE_CONFIG
from .music_producer import MUSIC_PRODUCTION_CONFIG
from .novel_producer import NOVEL_PRODUCTION_CONFIG
from .video_producer import VIDEO_PRODUCTION_CONFIG

__all__ = [
    "GENERAL_PURPOSE_CONFIG",
    "BASH_AGENT_CONFIG",
    "MUSIC_PRODUCTION_CONFIG",
    "NOVEL_PRODUCTION_CONFIG",
    "GAME_DESIGN_CONFIG",
    "VIDEO_PRODUCTION_CONFIG",
]

# Registry of built-in subagents
BUILTIN_SUBAGENTS = {
    "general-purpose": GENERAL_PURPOSE_CONFIG,
    "bash": BASH_AGENT_CONFIG,
    "music-producer": MUSIC_PRODUCTION_CONFIG,
    "novel-producer": NOVEL_PRODUCTION_CONFIG,
    "game-designer": GAME_DESIGN_CONFIG,
    "video-producer": VIDEO_PRODUCTION_CONFIG,
}
