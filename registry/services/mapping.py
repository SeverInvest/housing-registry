from __future__ import annotations

import logging
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from registry.models import ManagementBasis, ManagementMethod

logger = logging.getLogger(__name__)


def get_path(data: dict[str, Any], *path: str, default: Any = None) -> Any:
    current = data
    for part in path:
        if not isinstance(current, dict):
            return default
        current = current.get(part)
        if current is None:
            return default
    return current


def clean_text(value: Any) -> str:
    return " ".join(str(value or "").split())


def parse_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if not value:
        return None
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
        result = Decimal(str(value).replace(",", "."))
        return result if result.is_finite() else None
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
    normalized = clean_text(name).lower().replace("ё", "е")
    if not normalized:
        return ManagementMethod.UNKNOWN
    if "непосред" in normalized:
        return ManagementMethod.DIRECT
    if normalized in {"тсж", "тсн"} or "товариществ" in normalized:
        return ManagementMethod.HOA_TSN
    if normalized in {"жск", "жк"} or "кооператив" in normalized:
        return ManagementMethod.HOUSING_COOPERATIVE
    if normalized in {"уо", "ук"} or "управляющ" in normalized:
        return ManagementMethod.MANAGEMENT_COMPANY
    if "не выбран" in normalized:
        return ManagementMethod.NOT_SELECTED
    if normalized in {"иной способ", "иной", "другой", "other"}:
        return ManagementMethod.OTHER
    # Do not log the untrusted response value: it may contain sensitive data.
    logger.warning("Неизвестный способ управления: сохранено unknown")
    return ManagementMethod.UNKNOWN


def normalize_organization(data: dict[str, Any] | None) -> dict[str, Any] | None:
    if not data:
        return None
    return {
        "gis_guid": data.get("guid") or None,
        "ogrn": clean_text(data.get("ogrn")) or None,
        "inn": clean_text(data.get("inn")),
        "kpp": clean_text(data.get("kpp")),
        "full_name": clean_text(data.get("fullName") or data.get("shortName"))
        or "Организация без наименования",
        "short_name": clean_text(data.get("shortName")),
        "organization_type": clean_text(data.get("organizationType")),
        "legal_form": clean_text(get_path(data, "okopf", "name")),
        "legal_address": clean_text(data.get("orgAddress")),
        "phone": clean_text(data.get("phone")),
        "website": clean_text(data.get("url")),
    }


def build_address(fields: dict[str, Any], region_name: str) -> str:
    parts = [
        fields.get("postal_code"),
        region_name,
        fields.get("district"),
        fields.get("city") or fields.get("settlement"),
        fields.get("planning_structure_element"),
        fields.get("street"),
        fields.get("building_number"),
    ]
    return ", ".join(clean_text(part) for part in parts if clean_text(part))


def _address_fields(data: dict[str, Any], region_name: str) -> dict[str, Any]:
    address = data.get("address") or {}
    house = address.get("house") or {}
    fields = {
        "gis_address_guid": str(data.get("houseGuid") or house.get("guid") or ""),
        "fias_guid": house.get("houseGuid") or house.get("fiasHouseGuid") or None,
        "postal_code": clean_text(house.get("postalCode")),
        "district": clean_text(get_path(address, "district", "formalName")),
        "city": clean_text(get_path(address, "city", "formalName")),
        "settlement": clean_text(get_path(address, "settlement", "formalName")),
        "planning_structure_element": clean_text(
            get_path(address, "planningStructureElement", "formalName")
        ),
        "street": clean_text(get_path(address, "street", "formalName")),
        "building_number": clean_text(house.get("buildingNumber") or house.get("houseNumber")),
    }
    region_name = region_name or clean_text(get_path(address, "region", "formalName"))
    fields["address"] = build_address(fields, region_name)
    return fields


def normalize_search_item(item: dict[str, Any], *, region_name: str = "") -> dict[str, Any]:
    return {
        "gis_guid": item.get("guid"),
        **_address_fields(item, region_name),
        "house_type": clean_text(get_path(item, "houseType", "houseTypeName")),
        "cadastre_number": clean_text(item.get("cadastreNumber")),
        "condition": clean_text(get_path(item, "houseCondition", "houseCondition")),
    }


def normalize_detail(data: dict[str, Any], *, region_name: str = ""):
    material = data.get("intWallMaterialList") or ""
    if isinstance(material, list):
        material = ", ".join(
            clean_text(item.get("name")) if isinstance(item, dict) else clean_text(item)
            for item in material
        )
    house = {
        "gis_guid": data.get("guid"),
        **_address_fields(data, region_name),
        "house_uid": clean_text(data.get("houseUid")),
        "house_type": clean_text(get_path(data, "houseType", "houseTypeName")),
        "condition": clean_text(get_path(data, "houseCondition", "houseCondition")),
        "life_cycle_stage": clean_text(get_path(data, "lifeCycleStage", "lifeCycleStage")),
        "construction_year": parse_int(data.get("buildingYear")),
        "commissioning_year": parse_int(data.get("operationYear")),
        "reconstruction_year": parse_int(data.get("reconstructionYear")),
        "floors": parse_int(data.get("floorCount")),
        "wall_material": clean_text(material),
        "area_total": parse_decimal(data.get("totalSquare")),
        "area_residential": parse_decimal(data.get("residentialSquare")),
        # The separate premises-area keys need a verified source contract.
        # Do not copy residentialSquare into a different area indicator.
        "residential_premises_count": parse_int(data.get("residentialPremiseActualCount")),
        "non_residential_premises_count": parse_int(data.get("nonResidentialPremiseActualCount")),
        "cadastre_number": clean_text(data.get("cadastreNumber")),
    }
    management = {
        "management_method": normalize_management_method(
            get_path(data, "houseManagementType", "houseManagementTypeName")
        ),
        "management_basis": ManagementBasis.UNKNOWN,
        "date_start": parse_date(data.get("managementContractDate")),
        "date_finish": parse_date(data.get("endContractDate")),
    }
    organization = normalize_organization(data.get("managementOrganization"))
    if management["management_method"] == ManagementMethod.DIRECT:
        organization = None
    return house, organization, management
