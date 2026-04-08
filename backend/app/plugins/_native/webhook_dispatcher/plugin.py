"""
Webhook Dispatcher — native plugin.

Listens to collection and document lifecycle events and delivers HTTP POST
notifications to configured external endpoints.

Each registered endpoint can subscribe to one or more events. Delivery is
signed with HMAC-SHA256 when a secret is configured and retried up to 3
times with exponential backoff on transient network errors.

Configuration: Admin → /admin/webhooks
"""

from app.core.hooks import HookEvent, hook_registry
from app.core.plugin_base import PluginBase, PluginMeta
from app.models.collection import Collection
from app.plugins._native.webhook_dispatcher.router import router
from app.plugins._native.webhook_dispatcher.service import schedule_dispatch


def _collection_payload(col: Collection) -> dict:
    return {
        "collection_id": str(col.id),
        "slug": col.slug,
        "title": col.title,
        "is_public": col.is_public,
        "doc_count": col.doc_count,
        "status": col.status.value,
        "published_at": col.published_at.isoformat() if col.published_at else None,
    }


async def _on_collection_submitted(collection: Collection, **_: object) -> None:
    schedule_dispatch(HookEvent.ON_COLLECTION_SUBMITTED, _collection_payload(collection))


async def _on_collection_published(collection: Collection, **_: object) -> None:
    schedule_dispatch(HookEvent.ON_COLLECTION_PUBLISHED, _collection_payload(collection))


async def _on_collection_unpublished(collection: Collection, **_: object) -> None:
    schedule_dispatch(HookEvent.ON_COLLECTION_UNPUBLISHED, _collection_payload(collection))


async def _on_document_uploaded(collection: Collection, filename: str, **_: object) -> None:
    schedule_dispatch(
        HookEvent.ON_DOCUMENT_UPLOADED,
        {**_collection_payload(collection), "filename": filename},
    )


async def _on_document_deleted(collection: Collection, filename: str, **_: object) -> None:
    schedule_dispatch(
        HookEvent.ON_DOCUMENT_DELETED,
        {**_collection_payload(collection), "filename": filename},
    )


hook_registry.register(HookEvent.ON_COLLECTION_SUBMITTED, _on_collection_submitted)
hook_registry.register(HookEvent.ON_COLLECTION_PUBLISHED, _on_collection_published)
hook_registry.register(HookEvent.ON_COLLECTION_UNPUBLISHED, _on_collection_unpublished)
hook_registry.register(HookEvent.ON_DOCUMENT_UPLOADED, _on_document_uploaded)
hook_registry.register(HookEvent.ON_DOCUMENT_DELETED, _on_document_deleted)


class Plugin(PluginBase):
    meta = PluginMeta(
        id="webhook_dispatcher",
        name="Webhook Dispatcher",
        version="1.0.0",
        native=True,
        description=(
            "Delivers HTTP POST notifications to external endpoints on collection "
            "and document lifecycle events. Supports HMAC-SHA256 request signing "
            "and automatic retries."
        ),
        author="Aracne2 Team",
        min_role="Admin",
    )
    router = router
