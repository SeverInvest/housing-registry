from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from registry.models import ManagementMethod


def get_path(data: dict[str, Any], *path: str, default: Any = None) -> Any:
    current: Any = data
    for part in path:
        if not isinstance(current, dict):
            return default
        current = current.get(part)
        if current is None:
            return default
    return current


def parse_date(value: Any) -> date | None:
    if not value:
        return None
    if isinstance(value, date):
        return value
    for pattern in ("%d.%m.%Y", "%Y-%m-%d", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(str(value)[:19], pattern).date()
        except ValueError:
            continue
    return None


def parse_decimal(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value).replace(",", "."))
    except (InvalidOperation, ValueError):
        return None


def parse_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def normalize_management_method(name: str | None) -> str:
    normalized = (name or "").strip().lower().replace("ё", "е")
    if not normalized:
        return ManagementMethod.UNKNOWN
    if "непосред" in normalized:
        return ManagementMethod.DIRECT
    if any(token in normalized for token in ("тсж", "тсн", "жск", "жилищн", "кооператив")):
        return ManagementMethod.HOA_COOPERATIVE
    if normalized in {"уо", "ук"} or "управляющ" in normalized:
        return ManagementMethod.UO
    return ManagementMethod.UNKNOWN


def normalize_organization(data: dict[str, Any] | None) -> dict[str, Any] | None:
    if not data:
        return None
    return {
        "gis_guid": data.get("guid"),
        "registry_root_guid": data.get("registryOrganizationRootEntityGuid"),
        "ogrn": data.get("ogrn") or "",
        "inn": data.get("inn") or "",
        "full_name": data.get("fullName")
        or data.get("shortName")
        or "Организация без наименования",
        "short_name": data.get("shortName") or "",
        "organization_type": data.get("organizationType") or "",
        "okopf_code": get_path(data, "okopf", "code", default="") or "",
        "address": data.get("orgAddress") or "",
        "phone": data.get("phone") or "",
        "website": data.get("url") or "",
        "source_last_event_date": parse_date(data.get("lastEventDate")),
        "raw_data": data,
    }


def _address_fields(data: dict[str, Any]) -> dict[str, Any]:
    address = data.get("address") or {}
    house = address.get("house") or {}
    city = address.get("city") or {}
    settlement = address.get("settlement") or {}
    street = address.get("street") or {}
    oktmo = data.get("oktmo") or house.get("oktmo") or {}
    return {
        "gis_address_guid": data.get("houseGuid") or house.get("guid"),
        "fias_house_guid": house.get("houseGuid") or house.get("fiasHouseGuid"),
        "formatted_address": address.get("formattedAddress") or "",
        "postal_code": house.get("postalCode") or "",
        "region_name": get_path(address, "region", "formalName", default="") or "",
        "municipality_name": oktmo.get("name") or "",
        "locality_name": settlement.get("formalName") or city.get("formalName") or "",
        "street_name": street.get("formalName") or "",
        "oktmo": oktmo.get("code") or "",
    }


def normalize_search_item(
    item: dict[str, Any], *, forced_management_method: str | None = None
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    house_type = item.get("houseType") or {}
    raw_method = item.get("houseManagementType") or {}
    method_name = raw_method.get("houseManagementTypeName") or ""
    normalized: dict[str, Any] = {
        "gis_guid": item.get("guid"),
        **_address_fields(item),
        "house_type_code": house_type.get("code") or "",
        "house_type_name": house_type.get("houseTypeName") or "",
        "residential_premise_count": parse_int(
            item.get("residentialPremiseActualCount") or item.get("residentialPremiseCount")
        ),
        "non_residential_premise_count": parse_int(
            item.get("nonResidentialPremiseActualCount") or item.get("nonResidentialPremiseCount")
        ),
        "max_floor_count": parse_int(item.get("maxFloorCount")),
        "cadastre_number": item.get("cadastreNumber") or "",
        "house_condition": get_path(item, "houseCondition", "houseCondition", default="") or "",
        "source_status": item.get("status") or "",
        "approved": bool(item.get("approved")),
    }
    if forced_management_method or method_name:
        normalized.update(
            {
                "management_method": forced_management_method
                or normalize_management_method(method_name),
                "management_method_code": raw_method.get("code") or "",
                "management_method_name": method_name,
            }
        )
    return normalized, normalize_organization(item.get("managementOrganization"))


def normalize_detail(
    data: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    house_type = data.get("houseType") or {}
    raw_method = data.get("houseManagementType") or {}
    method_name = raw_method.get("houseManagementTypeName") or ""
    residential_count = data.get("residentialPremiseActualCount")
    non_residential_count = data.get("nonResidentialPremiseActualCount")
    normalized = {
        "gis_guid": data.get("guid"),
        **_address_fields(data),
        "house_uid": data.get("houseUid") or "",
        "house_type_code": house_type.get("code") or "",
        "house_type_name": house_type.get("houseTypeName") or "",
        "management_method": normalize_management_method(method_name),
        "management_method_code": raw_method.get("code") or "",
        "management_method_name": method_name,
        "management_start_date": parse_date(data.get("managementContractDate")),
        "management_end_date": parse_date(data.get("endContractDate")),
        "total_square": parse_decimal(data.get("totalSquare")),
        "residential_square": parse_decimal(data.get("residentialSquare")),
        "residential_premise_count": parse_int(residential_count),
        "non_residential_premise_count": parse_int(non_residential_count),
        "min_floor_count": parse_int(data.get("minFloorCount")),
        "max_floor_count": parse_int(data.get("floorCount") or data.get("maxFloorCount")),
        "underground_floor_count": parse_int(data.get("undergroundFloorCount")),
        "building_year": parse_int(data.get("buildingYear")),
        "operation_year": parse_int(data.get("operationYear")),
        "reconstruction_year": parse_int(data.get("reconstructionYear")),
        "cadastre_number": data.get("cadastreNumber") or "",
        "wall_material": data.get("intWallMaterialList") or "",
        "house_condition": get_path(data, "houseCondition", "houseCondition", default="") or "",
        "life_cycle_stage": get_path(data, "lifeCycleStage", "lifeCycleStage", default="") or "",
        "source_status": data.get("status") or "",
        "approved": bool(data.get("approved")),
    }
    return normalized, normalize_organization(data.get("managementOrganization"))


def json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    if isinstance(value, (date, datetime, Decimal)):
        return str(value)
    return value


def content_hash(value: dict[str, Any]) -> str:
    encoded = json.dumps(
        json_safe(value), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def changed_fields(previous: dict[str, Any] | None, current: dict[str, Any]) -> list[str]:
    if previous is None:
        return sorted(current.keys())
    return sorted(
        key for key in set(previous) | set(current) if previous.get(key) != current.get(key)
    )
