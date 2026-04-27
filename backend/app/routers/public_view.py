"""public_view router — unauthenticated public browsing endpoints.

All routes in this router require no authentication.  They expose only
published, is_public=True collections.
"""

import mimetypes
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from sqlalchemy import select

from app.db.postgres import get_async_session
from app.plugins._native.named_entities.models import EntityOccurrence, NamedEntity
from app.services import media as media_svc
from app.services.lod import (
    collection_to_graph,
    document_to_graph,
    negotiate_rdf,
    serialize_graph,
)
from app.services.public_view import (
    get_public_collection,
    get_public_collection_detail,
    render_document_html,
)

router = APIRouter(prefix="/public", tags=["public"])


def _public_base_url(request: Request) -> str:
    """Canonical site origin used as the prefix for emitted LOD URIs.

    Derived from the incoming request — a reverse proxy that sets
    ``X-Forwarded-Proto`` / ``X-Forwarded-Host`` via FastAPI's
    ``ProxyHeadersMiddleware`` gives us the real public origin in
    production; in local dev the backend port sneaks in, but LOD
    consumers testing locally understand that.
    """
    return f"{request.url.scheme}://{request.url.netloc}"


async def _orcid_map(db: AsyncSession) -> dict[str, str]:
    """Collect every User with an ORCID as a name→ORCID lookup.

    Keys the map by both ``display_name`` and ``username`` so either
    form in ``Collection.author`` / ``document.author`` can match.
    The deployment is invite-only so this is a tiny table (tens of
    rows) — issuing the query on every LOD request is cheap and
    sidesteps the cache-invalidation problem on profile edits.
    """
    from app.models.user import User

    rows = list(
        await db.scalars(select(User).where(User.orcid.is_not(None)))
    )
    out: dict[str, str] = {}
    for u in rows:
        if u.orcid:
            if u.display_name:
                out[u.display_name] = u.orcid
            out[u.username] = u.orcid
    return out


@router.get("/collections/{slug}")
async def public_collection_detail(
    slug: str,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> Response:
    """Return metadata and document list for a published public collection.

    Content-negotiated output:

    - ``Accept: text/turtle`` → Turtle RDF
    - ``Accept: application/rdf+xml`` → RDF/XML
    - ``Accept: application/ld+json`` → JSON-LD (RDF serialisation)
    - anything else (``application/json``, ``*/*``, missing, …) → the
      platform's ``{"data": PublicCollectionDetail}`` JSON envelope,
      unchanged behaviour for the SPA and existing API consumers.

    See docs/reference/LOD_INTEGRATION.md for the RDF vocabularies used
    (schema.org + Dublin Core mirrors).
    """
    data = await get_public_collection_detail(db, slug)

    negotiated = negotiate_rdf(request.headers.get("accept"))
    if negotiated is not None:
        fmt, mime = negotiated
        graph = collection_to_graph(
            base_url=_public_base_url(request),
            slug=data.slug,
            title=data.title,
            description=data.description,
            author=data.author,
            publisher=data.publisher,
            pub_year=data.pub_year,
            documents=[d.model_dump() for d in data.documents],
            orcid_by_name=await _orcid_map(db),
        )
        return Response(content=serialize_graph(graph, fmt), media_type=mime)

    return JSONResponse({"data": data.model_dump(mode="json")})


@router.get("/collections/{slug}/documents/{filename}")
async def public_document_render(
    slug: str,
    filename: str,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> Response:
    """Render a document (HTML by default) with RDF content negotiation.

    Response shape picked from the Accept header:

    - ``Accept: text/turtle`` / ``application/rdf+xml`` /
      ``application/ld+json`` → document graph serialised in the
      requested format. The graph includes the document's named
      entities with ``schema:sameAs`` pointing to their Wikidata
      (or VIAF / GeoNames) authority URIs when the editor has
      resolved them via the LOD.1c sidebar.
    - anything else → HTML rendered via the built-in TEI XSLT stylesheet,
      served with ``Content-Type: text/html`` so the SPA can embed it
      in an iframe unchanged.
    """
    negotiated = negotiate_rdf(request.headers.get("accept"))
    if negotiated is not None:
        fmt, mime = negotiated
        collection = await get_public_collection(db, slug)
        # Document metadata — pulled from the collection detail only to
        # resolve the document's title/author (the ORM Collection row
        # does not know per-document titles).
        detail = await get_public_collection_detail(db, slug)
        doc_meta = next(
            (d for d in detail.documents if d.filename == filename), None
        )
        # Entities referenced by this specific document (joined with the
        # catalog so we get the canonical form and authority_ref).
        stmt = (
            select(NamedEntity)
            .join(EntityOccurrence, EntityOccurrence.entity_id == NamedEntity.id)
            .where(
                EntityOccurrence.collection_id == collection.id,
                EntityOccurrence.filename == filename,
            )
            .distinct()
        )
        entities = [
            {
                "type": e.type,
                "canonical_form": e.canonical_form,
                "authority_ref": e.authority_ref,
            }
            for e in await db.scalars(stmt)
        ]
        graph = document_to_graph(
            base_url=_public_base_url(request),
            slug=slug,
            filename=filename,
            document_title=doc_meta.title if doc_meta else None,
            document_author=doc_meta.author if doc_meta else None,
            collection_title=collection.title,
            collection_author=collection.author,
            collection_publisher=collection.publisher,
            collection_pub_year=collection.pub_year,
            entities=entities,
            orcid_by_name=await _orcid_map(db),
        )
        return Response(content=serialize_graph(graph, fmt), media_type=mime)

    html = await render_document_html(db, slug, filename)
    return HTMLResponse(content=html)


@router.get("/collections/{slug}/documents/{filename}/source")
async def public_document_source(
    slug: str,
    filename: str,
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> Response:
    """Return the raw TEI XML of a public document as an attachment.

    Same access rules as the rendered HTML endpoint: the collection
    must be published AND publicly visible. ``Content-Disposition:
    attachment`` makes the click a download rather than an inline
    render.
    """
    from app.db.existdb import existdb_client
    from app.core.exceptions import NotFoundError as _NotFound

    await get_public_collection(db, slug)
    try:
        xml_bytes = await existdb_client.get_document(slug, filename)
    except Exception as exc:
        raise _NotFound(f"Document '{filename}' not found.") from exc
    return Response(
        content=xml_bytes,
        media_type="application/xml",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/collections/{slug}/documents/{doc_filename}/media/{filename}")
async def public_serve_document_media(
    slug: str,
    doc_filename: str,
    filename: str,
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> FileResponse:
    """Serve a document media file without authentication.

    Requires the collection to be published and publicly accessible.
    This endpoint is used by the XSLT-rendered website and static builds
    to load images embedded via <graphic url="…"/> in TEI documents.
    """
    await get_public_collection(db, slug)
    path = media_svc.get_media_path(slug, doc_filename, filename)
    media_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    return FileResponse(path, media_type=media_type)
