"""
OAI-PMH Provider — native plugin.

Exposes published public collections as an OAI-PMH 2.0-compliant repository,
enabling metadata harvesters (DART, OpenDOAR aggregators, Europeana, etc.) to
collect Dublin Core records for all documents.

Each published public collection is exposed as an OAI-PMH set; each XML document
within it becomes a record with Dublin Core metadata derived from its TEI header
(with fallback to collection-level metadata stored in PostgreSQL).

Endpoint: GET /api/v1/oai?verb=<Verb>
"""

from app.core.plugin_base import PluginBase, PluginMeta
from app.plugins._native.oai_pmh.router import router


class Plugin(PluginBase):
    meta = PluginMeta(
        id="oai_pmh",
        name="OAI-PMH Provider",
        version="1.0.0",
        native=True,
        description=(
            "Exposes published collections as an OAI-PMH 2.0 repository. "
            "Supports Dublin Core (oai_dc) metadata harvested from TEI headers. "
            "Endpoint: GET /api/v1/oai?verb=Identify"
        ),
        author="Aracne2 Team",
        min_role="Admin",
    )
    router = router
