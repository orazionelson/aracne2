"""
ExistDBClient — async HTTP client for eXist-db 6.x REST API.

All collection and document paths are rooted at _DB_ROOT so that Aracne2
data is cleanly namespaced inside the eXist-db instance.

Collection slug  →  eXist-db path
  "dante"        →  /db/aracne2/collections/dante

XQuery files are loaded from app/xqueries/ — never built inline.
All XML parsing uses defusedxml (XXE prevention).
"""

from pathlib import Path
from urllib.parse import urlencode

import defusedxml.ElementTree as ET
import httpx
import structlog

from app.config import settings
from app.core.exceptions import ExternalServiceError, NotFoundError

logger = structlog.get_logger()

_REST = "/exist/rest"
_DB_ROOT = "/db/aracne2"
_XQUERIES_DIR = Path(__file__).parent.parent / "xqueries"


class ExistDBClient:
    _client: httpx.AsyncClient | None = None

    # ── Lifecycle ──────────────────────────────────────────────────────────────

    async def connect(self) -> None:
        self._client = httpx.AsyncClient(
            base_url=settings.existdb_url,
            auth=(settings.existdb_user, settings.exist_password),
            timeout=30.0,
        )

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    async def ping(self) -> bool:
        """GET /exist/rest/ — returns True if reachable, False otherwise."""
        if not self._client:
            return False
        try:
            r = await self._client.get(f"{_REST}/")
            return r.status_code == 200
        except Exception:
            return False

    async def ensure_root(self) -> None:
        """Create /db/aracne2 and /db/aracne2/collections if absent.

        Safe to call at every startup — the XQuery is fully idempotent.
        """
        await self.xquery("system/ensure_root.xq")

    # ── Internal helpers ───────────────────────────────────────────────────────

    def _require(self) -> httpx.AsyncClient:
        if not self._client:
            raise ExternalServiceError("existdb", "Client not connected")
        return self._client

    def col_path(self, slug: str) -> str:
        """Full eXist-db path for a collection slug."""
        return f"{_DB_ROOT}/collections/{slug}"

    def _rest_url(self, *segments: str) -> str:
        """Build a REST URL: /exist/rest + joined segments."""
        return _REST + "".join(f"/{s.strip('/')}" for s in segments if s)

    def _load_xq(self, query_file: str) -> str:
        """Load an XQuery file from app/xqueries/."""
        path = _XQUERIES_DIR / query_file
        try:
            return path.read_text(encoding="utf-8")
        except FileNotFoundError:
            raise ExternalServiceError("existdb", f"XQuery file not found: {query_file}")

    # ── XQuery execution ───────────────────────────────────────────────────────

    async def xquery(
        self, query_file: str, variables: dict[str, str] | None = None
    ) -> bytes:
        """Execute an XQuery from app/xqueries/ and return raw response bytes."""
        query = self._load_xq(query_file)
        client = self._require()

        form: dict[str, str] = {"_query": query, "_wrap": "no"}
        if variables:
            form.update(variables)

        r = await client.post(
            self._rest_url("db"),
            content=urlencode(form).encode(),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        if r.status_code not in (200, 201):
            raise ExternalServiceError(
                "existdb", f"XQuery '{query_file}' failed ({r.status_code}): {r.text[:300]}"
            )
        return r.content

    # ── Collection operations ──────────────────────────────────────────────────

    async def collection_exists(self, slug: str) -> bool:
        """Return True if the collection exists in eXist-db."""
        client = self._require()
        r = await client.get(
            self._rest_url(_DB_ROOT, "collections", slug),
            headers={"Accept": "application/xml"},
        )
        return r.status_code == 200

    async def create_collection(self, slug: str) -> None:
        """Create /db/aracne2/collections/{slug} in eXist-db."""
        await self.xquery(
            "system/create_collection.xq",
            {"root": f"{_DB_ROOT}/collections", "name": slug},
        )
        logger.info("existdb_collection_created", slug=slug)

    async def delete_collection(self, slug: str) -> None:
        """Recursively delete /db/aracne2/collections/{slug} from eXist-db."""
        await self.xquery(
            "system/delete_collection.xq",
            {"path": self.col_path(slug)},
        )
        logger.info("existdb_collection_deleted", slug=slug)

    async def list_collection(self, slug: str) -> list[str]:
        """Return filenames of all XML documents in the collection."""
        client = self._require()
        r = await client.get(
            self._rest_url(_DB_ROOT, "collections", slug) + "/",
            headers={"Accept": "application/xml"},
        )
        if r.status_code == 404:
            return []
        if r.status_code != 200:
            raise ExternalServiceError(
                "existdb", f"list_collection failed ({r.status_code})"
            )

        ns = "http://exist.sourceforge.net/NS/exist"
        root = ET.fromstring(r.text)
        return [
            el.get("name", "")
            for el in root.iter(f"{{{ns}}}resource")
            if el.get("name", "").endswith(".xml")
        ]

    # ── Document operations ────────────────────────────────────────────────────

    async def get_document(self, slug: str, filename: str) -> bytes:
        """Fetch a raw XML document from eXist-db."""
        client = self._require()
        r = await client.get(
            self._rest_url(_DB_ROOT, "collections", slug, filename),
            headers={"Accept": "application/xml"},
        )
        if r.status_code == 404:
            raise NotFoundError(f"Document '{filename}' not found in '{slug}'")
        if r.status_code != 200:
            raise ExternalServiceError(
                "existdb", f"get_document failed ({r.status_code})"
            )
        return r.content

    async def put_document(self, slug: str, filename: str, xml_bytes: bytes) -> None:
        """Store or overwrite an XML document in eXist-db."""
        client = self._require()
        r = await client.put(
            self._rest_url(_DB_ROOT, "collections", slug, filename),
            content=xml_bytes,
            headers={"Content-Type": "application/xml"},
        )
        if r.status_code not in (200, 201):
            raise ExternalServiceError(
                "existdb", f"put_document failed ({r.status_code}): {r.text[:300]}"
            )
        logger.info("existdb_document_stored", slug=slug, filename=filename)

    async def delete_document(self, slug: str, filename: str) -> None:
        """Delete a document from eXist-db."""
        client = self._require()
        r = await client.delete(
            self._rest_url(_DB_ROOT, "collections", slug, filename)
        )
        if r.status_code not in (200, 204):
            raise ExternalServiceError(
                "existdb", f"delete_document failed ({r.status_code})"
            )
        logger.info("existdb_document_deleted", slug=slug, filename=filename)

    # ── Kept for backward compatibility with existing stubs ───────────────────

    async def store_document(
        self,
        collection_path: str,
        filename: str,
        xml_bytes: bytes,
        create_if_missing: bool = True,
    ) -> str:
        """Alias for put_document — uses slug extracted from collection_path."""
        slug = collection_path.rstrip("/").split("/")[-1]
        await self.put_document(slug, filename, xml_bytes)
        return filename


existdb_client = ExistDBClient()


async def get_existdb() -> ExistDBClient:
    return existdb_client
