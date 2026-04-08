"""
AI Integration — native plugin.

Provides LLM-assisted workflows for document editing, validation error
analysis, and XSLT debugging.  Supports OpenAI, Anthropic and Google Gemini
via a unified streaming interface.

This is a native plugin: it cannot be deactivated.
Configure the active provider and API keys in Settings → AI.
"""

from app.core.plugin_base import PluginBase, PluginMeta
from app.plugins._native.ai.router import router


class Plugin(PluginBase):
    meta = PluginMeta(
        id="ai",
        name="AI Integration",
        version="1.0.0",
        native=True,
        description=(
            "LLM-assisted workflows: validation error analysis, document encoding "
            "suggestions, and XSLT debugging. Supports OpenAI, Anthropic and Gemini."
        ),
        author="Aracne2 Team",
        min_role="Editor",
    )
    router = router
