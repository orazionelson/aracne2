import httpx

from app.config import settings


class ExistDBClient:
    _client: httpx.AsyncClient | None = None

    async def connect(self) -> None:
        self._client = httpx.AsyncClient(
            base_url=settings.existdb_url,
            auth=(settings.existdb_user, settings.exist_password),
            timeout=30.0,
            headers={"Accept": "application/json"},
        )

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()

    async def ping(self) -> bool:
        """GET /exist/rest/ — returns True if 200, False otherwise. Never raises."""
        if not self._client:
            return False
        try:
            r = await self._client.get("/exist/rest/")
            return r.status_code == 200
        except Exception:
            return False

    # Stubs — implemented in PHASE 05
    async def xquery(
        self, query_name: str, params: dict[str, object] | None = None
    ) -> dict[str, object]:
        raise NotImplementedError("Implemented in PHASE 05")

    async def store_document(
        self,
        collection_path: str,
        filename: str,
        xml_bytes: bytes,
        create_if_missing: bool = True,
    ) -> str:
        raise NotImplementedError("Implemented in PHASE 05")

    async def delete_document(self, collection_path: str, filename: str) -> None:
        raise NotImplementedError("Implemented in PHASE 05")

    async def create_collection(self, path: str) -> None:
        raise NotImplementedError("Implemented in PHASE 05")

    async def collection_exists(self, path: str) -> bool:
        raise NotImplementedError("Implemented in PHASE 05")

    async def list_collection(self, path: str) -> list[str]:
        raise NotImplementedError("Implemented in PHASE 05")


existdb_client = ExistDBClient()


async def get_existdb() -> ExistDBClient:
    return existdb_client
