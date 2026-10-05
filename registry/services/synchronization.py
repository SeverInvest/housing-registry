from __future__ import annotations

import time

from registry.models import House
from registry.services.api import GISHousingAPIError, build_search_payload
from registry.services.mapping import normalize_detail
from registry.services.persistence import DetailResult, persist_detail


def search_pages(client, region_guid, house_type, *, max_pages=None, pause=0):
    page_index = 0
    processed = 0
    total = None
    while max_pages is None or page_index < max_pages:
        data = client.search_houses(
            page_index=page_index,
            elements_per_page=100,
            payload=build_search_payload(
                region_guid, calc_count=page_index == 0, house_type_refs=[house_type]
            ),
        )
        items = data.get("items") or []
        if not items:
            return
        if len(items) > 100:
            raise GISHousingAPIError("Поисковая страница содержит более 100 записей")
        if data.get("total") is not None:
            total = int(data["total"])
        processed += len(items)
        yield items
        page_index += 1
        if (total is not None and processed >= total) or data.get("last") is True:
            return
        if pause:
            time.sleep(pause)


def fetch_missing_detail(client, house: House, *, type_code="1") -> DetailResult:
    house.refresh_from_db(fields=("detail_fetched_at",))
    if house.detail_fetched_at is not None:
        return DetailResult()
    payload = client.house_detail(type_code=type_code, guid=str(house.gis_guid))
    normalized, organization, management = normalize_detail(payload, region_name=house.region.name)
    return persist_detail(
        house=house, normalized=normalized, organization_data=organization, management=management
    )
