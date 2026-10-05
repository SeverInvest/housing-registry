from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from django.db import transaction
from django.utils import timezone

from registry.models import (
    House,
    HouseManagement,
    ManagementBasis,
    ManagementMethod,
    ManagementSource,
    Organization,
    Region,
)


@dataclass(frozen=True)
class DetailResult:
    fetched: bool = False
    organization_created: bool = False
    management_created: bool = False


HOUSE_FIELDS = {
    field.name
    for field in House._meta.fields
    if field.name
    not in {"id", "region", "gis_guid", "created_at", "updated_at", "detail_fetched_at"}
}


@transaction.atomic
def _upsert_organization(data: dict[str, Any] | None) -> tuple[Organization | None, bool]:
    if not data:
        return None, False
    organization = None
    for key in ("ogrn", "gis_guid"):
        if data.get(key):
            organization = (
                Organization.objects.select_for_update().filter(**{key: data[key]}).first()
            )
            if organization is not None:
                break
    if organization is None and data.get("inn") and data.get("kpp"):
        candidates = Organization.objects.select_for_update().filter(
            inn=data["inn"], kpp=data["kpp"]
        )
        if candidates.count() > 1:
            raise ValueError("Неоднозначное сопоставление организации по ИНН и КПП")
        organization = candidates.first()
    created = organization is None
    if created:
        organization = Organization(full_name=data["full_name"])
    for field, value in data.items():
        if value not in (None, ""):
            setattr(organization, field, value)
    # Optional unique strings are represented by NULL rather than an empty string.
    organization.ogrn = organization.ogrn or None
    organization.full_clean()
    organization.save()
    return organization, created


def upsert_organization(data: dict[str, Any] | None) -> Organization | None:
    return _upsert_organization(data)[0]


@transaction.atomic
def update_management(
    *,
    house: House,
    organization: Organization | None,
    management_method: str,
    source: str,
    management_basis: str = ManagementBasis.UNKNOWN,
    date_start=None,
    date_finish=None,
    previous_finish_date=None,
) -> tuple[HouseManagement, bool]:
    House.objects.select_for_update().get(pk=house.pk)
    if management_method == ManagementMethod.DIRECT and organization is not None:
        raise ValueError("При непосредственном управлении организация должна быть пустой")
    current = (
        HouseManagement.objects.select_for_update().filter(house=house, is_active=True).first()
    )
    organization_id = organization.pk if organization else None
    if (
        current
        and current.organization_id == organization_id
        and current.management_method == management_method
    ):
        changed = False
        for field, value in {
            "date_start": date_start,
            "date_finish": date_finish,
            "management_basis": management_basis,
        }.items():
            if value is None or (field == "management_basis" and value == ManagementBasis.UNKNOWN):
                continue
            if getattr(current, field) != value:
                setattr(current, field, value)
                changed = True
        if changed:
            current.source = source
            current.full_clean()
            current.save()
        return current, False
    if current:
        current.is_active = False
        if previous_finish_date is not None:
            current.date_finish = previous_finish_date
        current.full_clean()
        current.save()
    period = HouseManagement(
        house=house,
        organization=organization,
        management_method=management_method,
        management_basis=management_basis,
        date_start=date_start,
        date_finish=date_finish,
        source=source,
    )
    period.full_clean()
    period.save()
    return period, True


@transaction.atomic
def ensure_search_house(*, region: Region, normalized: dict[str, Any]) -> tuple[House, bool]:
    guid = normalized.get("gis_guid")
    if not guid:
        raise ValueError("В поисковой записи отсутствует GUID дома")
    defaults = {key: value for key, value in normalized.items() if key in HOUSE_FIELDS}
    house, created = House.objects.get_or_create(
        gis_guid=guid, defaults={"region": region, **defaults}
    )
    if house.region_id != region.pk:
        raise ValueError("Дом уже относится к другому региону")
    return house, created


@transaction.atomic
def persist_detail(
    *,
    house: House,
    normalized: dict[str, Any],
    organization_data: dict[str, Any] | None,
    management: dict[str, Any],
) -> DetailResult:
    house = House.objects.select_for_update().get(pk=house.pk)
    if house.detail_fetched_at is not None:
        return DetailResult()
    if str(normalized.get("gis_guid")) != str(house.gis_guid):
        raise ValueError("GUID подробной карточки не совпадает с GUID дома")
    organization, organization_created = _upsert_organization(organization_data)
    for field, value in normalized.items():
        if field in HOUSE_FIELDS and value not in (None, ""):
            setattr(house, field, value)
    house.full_clean()
    house.save()
    _, management_created = update_management(
        house=house, organization=organization, source=ManagementSource.GIS_DETAIL, **management
    )
    house.detail_fetched_at = timezone.now()
    house.save(update_fields=("detail_fetched_at", "updated_at"))
    return DetailResult(True, organization_created, management_created)
