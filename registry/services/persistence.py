from __future__ import annotations

from typing import Any

from django.db import transaction
from django.utils import timezone

from registry.models import House, HouseVersion, ImportRun, ImportSource, Organization, Region
from registry.services.mapping import changed_fields, content_hash, json_safe

HOUSE_UPDATE_FIELDS = {
    field.name
    for field in House._meta.fields
    if field.name
    not in {
        "id",
        "gis_guid",
        "created_at",
        "updated_at",
        "first_seen_at",
        "last_seen_at",
        "detail_fetched_at",
        "needs_detail_refresh",
        "search_hash",
        "detail_hash",
        "search_payload",
        "detail_payload",
        "management_organization",
    }
}


def upsert_organization(data: dict[str, Any] | None) -> Organization | None:
    if not data:
        return None
    gis_guid = data.get("gis_guid")
    ogrn = data.get("ogrn") or ""
    organization = None
    if gis_guid:
        organization = Organization.objects.filter(gis_guid=gis_guid).first()
    if organization is None and ogrn:
        organization = Organization.objects.filter(ogrn=ogrn).order_by("id").first()
    if organization is None:
        organization = Organization(gis_guid=gis_guid, full_name=data["full_name"])

    for field, value in data.items():
        if field == "raw_data" or value not in (None, ""):
            setattr(organization, field, value)
    organization.save()
    return organization


@transaction.atomic
def persist_house(
    *,
    region: Region,
    normalized: dict[str, Any],
    organization_data: dict[str, Any] | None,
    raw_payload: dict[str, Any],
    source: str,
    run: ImportRun,
) -> tuple[House, str]:
    gis_guid = normalized.get("gis_guid")
    if not gis_guid:
        raise ValueError("В записи отсутствует guid объекта ГИС ЖКХ")

    organization = upsert_organization(organization_data)
    house, created = House.objects.select_for_update().get_or_create(
        gis_guid=gis_guid,
        defaults={
            "region": region,
            "formatted_address": normalized.get("formatted_address") or str(gis_guid),
        },
    )
    if house.region_id != region.id:
        raise ValueError(
            f"Дом {gis_guid} уже относится к региону {house.region}; получен регион {region}"
        )
    now = timezone.now()
    is_search = source == ImportSource.GIS_SEARCH
    hash_field = "search_hash" if is_search else "detail_hash"
    payload_field = "search_payload" if is_search else "detail_payload"

    snapshot = json_safe(
        {
            **normalized,
            "region_code": region.code,
            "region_fias_guid": str(region.fias_guid),
            "management_organization_ogrn": organization.ogrn if organization else None,
            "management_organization_guid": str(organization.gis_guid)
            if organization and organization.gis_guid
            else None,
        }
    )
    new_hash = content_hash(snapshot)
    old_hash = getattr(house, hash_field)

    if created or new_hash != old_hash:
        previous = (
            HouseVersion.objects.filter(house=house, source=source)
            .order_by("-observed_at")
            .values_list("snapshot", flat=True)
            .first()
        )
        HouseVersion.objects.create(
            house=house,
            run=run,
            source=source,
            content_hash=new_hash,
            changed_fields=changed_fields(previous, snapshot),
            snapshot=snapshot,
        )

    for field, value in normalized.items():
        if field in HOUSE_UPDATE_FIELDS:
            if is_search and value in (None, ""):
                continue
            setattr(house, field, value)
    house.management_organization = organization
    house.active = True
    house.consecutive_missing_runs = 0
    house.last_missing_at = None
    house.last_seen_at = now
    setattr(house, hash_field, new_hash)
    setattr(house, payload_field, raw_payload)

    if is_search:
        if created or new_hash != old_hash:
            house.needs_detail_refresh = True
    else:
        house.detail_fetched_at = now
        house.needs_detail_refresh = False

    house.save()
    if created:
        outcome = "created"
    elif new_hash != old_hash:
        outcome = "updated"
    else:
        outcome = "unchanged"
    return house, outcome
