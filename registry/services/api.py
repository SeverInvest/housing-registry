from __future__ import annotations

import time
import uuid
from typing import Any

import httpx
from django.conf import settings

MKD_HOUSE_TYPE_REF = {
    "guid": "55a9b133-24eb-456f-85c4-134624646a8d",
    "code": "1",
    "houseTypeName": "Многоквартирный",
}


def build_search_payload(
    region_guid: str,
    *,
    calc_count: bool,
    house_type_refs: list[dict[str, Any]] | None = None,
    management_type_refs: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Payload observed in the public GIS Housing API.

    Reference objects are deliberately configurable: the public UI may change
    dictionary versions while keeping the endpoint stable.
    """

    return {
        "regionCode": region_guid,
        "fiasHouseCodeList": None,
        "estStatus": None,
        "strStatus": None,
        "calcCount": calc_count,
        "houseConditionRefList": None,
        "houseTypeRefList": house_type_refs,
        "houseManagementTypeRefList": management_type_refs,
        "cadastreNumber": None,
        "oktmo": None,
        "statuses": ["APPROVED"],
        "regionProperty": None,
        "municipalProperty": None,
        "hostelTypeCodes": None,
        "useReadOnlyDataSource": True,
    }


class GISHousingAPIError(RuntimeError):
    pass


class GISHousingClient:
    def __init__(
        self,
        *,
        base_url: str | None = None,
        timeout: float | None = None,
        max_retries: int | None = None,
    ) -> None:
        self.base_url = (base_url or settings.GIS_API_BASE_URL).rstrip("/")
        self.timeout = timeout or settings.GIS_REQUEST_TIMEOUT
        self.max_retries = max_retries if max_retries is not None else settings.GIS_MAX_RETRIES
        self.session_guid = str(uuid.uuid4())
        self.client = httpx.Client(
            base_url=self.base_url,
            timeout=self.timeout,
            follow_redirects=True,
            headers={
                "Accept": "application/json; charset=utf-8",
                "Content-Type": "application/json;charset=UTF-8",
                "Origin": self.base_url,
                "Referer": f"{self.base_url}/",
                "State-GUID": "/houses",
                "Session-GUID": self.session_guid,
                "User-Agent": "Twayli-Housing-Registry/0.1 (+public GIS Housing data)",
            },
        )

    def __enter__(self) -> GISHousingClient:
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()

    def close(self) -> None:
        self.client.close()

    def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        for attempt in range(self.max_retries + 1):
            try:
                response = self.client.request(
                    method,
                    path,
                    headers={"Request-GUID": str(uuid.uuid4())},
                    **kwargs,
                )
                if response.status_code == 429 or response.status_code >= 500:
                    raise GISHousingAPIError(
                        f"Временная ошибка ГИС ЖКХ: HTTP {response.status_code}"
                    )
                response.raise_for_status()
                data = response.json()
                if not isinstance(data, dict):
                    raise GISHousingAPIError("ГИС ЖКХ вернула JSON неожиданного типа")
                return data
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code < 500 and exc.response.status_code != 429:
                    raise GISHousingAPIError(
                        f"ГИС ЖКХ отклонила запрос: HTTP {exc.response.status_code}"
                    ) from None
                if attempt >= self.max_retries:
                    break
                time.sleep(min(2**attempt, 15))
            except (httpx.HTTPError, ValueError, GISHousingAPIError):
                if attempt >= self.max_retries:
                    break
                time.sleep(min(2**attempt, 15))
        raise GISHousingAPIError("Не удалось получить корректный ответ ГИС ЖКХ") from None

    def search_houses(
        self, *, page_index: int, elements_per_page: int, payload: dict[str, Any]
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            "/homemanagement/api/rest/services/houses/public/searchByAddress",
            params={"pageIndex": page_index, "elementsPerPage": elements_per_page},
            json=payload,
        )

    def house_detail(self, *, type_code: str, guid: str) -> dict[str, Any]:
        return self._request(
            "GET",
            f"/homemanagement/api/rest/services/houses/public/{type_code}/{guid}",
        )
