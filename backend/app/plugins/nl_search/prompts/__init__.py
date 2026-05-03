"""System prompts for the natural-language search orchestrator."""

from pathlib import Path

_PROMPT_DIR = Path(__file__).parent

_SUPPORTED_LANGS: tuple[str, ...] = ("en", "it")


def load_system_prompt(lang: str) -> str:
    """Return the system prompt for the requested language.

    Falls back to English when the requested language has no prompt
    file. The text is loaded from disk at import time? No — every
    request reloads, but the prompts are tiny (~1 KB) and the cost is
    negligible compared to the LLM round-trip.
    """
    target = (lang or "en").split("-")[0].lower()
    if target not in _SUPPORTED_LANGS:
        target = "en"
    path = _PROMPT_DIR / f"system_prompt_{target}.md"
    if not path.is_file():
        path = _PROMPT_DIR / "system_prompt_en.md"
    return path.read_text(encoding="utf-8").strip()


__all__ = ["load_system_prompt"]
