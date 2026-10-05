from __future__ import annotations

import json
import time

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from registry.models import Region
from registry.services.api import MKD_HOUSE_TYPE_REF, GISHousingClient
from registry.services.mapping import normalize_search_item
from registry.services.persistence import ensure_search_house
from registry.services.synchronization import fetch_missing_detail, search_pages


class Command(BaseCommand):
    help = "Находит новые дома по регионам и получает только отсутствующие подробные карточки"

    def add_arguments(self, parser):
        parser.add_argument("--region-code", default=settings.GIS_REGION_CODE)
        parser.add_argument("--region-guid", default=settings.GIS_REGION_GUID)
        parser.add_argument("--page-size", type=int, choices=(100,), default=100)
        parser.add_argument("--max-pages", type=int)
        parser.add_argument("--sleep", type=float, default=0.25)
        parser.add_argument("--house-type-ref-json", default=json.dumps(MKD_HOUSE_TYPE_REF))

    def handle(self, *args, **options):
        if options["sleep"] < 0 or (options["max_pages"] is not None and options["max_pages"] < 1):
            raise CommandError(
                "Пауза должна быть неотрицательной; max-pages должен быть положительным"
            )
        try:
            house_type = json.loads(options["house_type_ref_json"])
        except ValueError as exc:
            raise CommandError("Некорректный JSON справочника типа дома") from exc
        if not isinstance(house_type, dict) or not house_type.get("code"):
            raise CommandError("Справочник типа дома должен содержать code")
        regions = Region.objects.filter(sync_enabled=True).order_by("code")
        if options["region_code"]:
            regions = regions.filter(code=options["region_code"])
        if options["region_guid"]:
            regions = regions.filter(fias_guid=options["region_guid"])
        if not regions.exists():
            raise CommandError("Не найдены регионы с включённой синхронизацией")
        stats = {
            key: 0
            for key in (
                "pages",
                "found",
                "houses_created",
                "skipped",
                "details_fetched",
                "detail_errors",
                "organizations_created",
                "management_created",
                "errors",
            )
        }
        with GISHousingClient() as client:
            for region in regions:
                if region.fias_guid is None:
                    stats["errors"] += 1
                    self.stderr.write(f"Регион {region.code}: не задан FIAS GUID")
                    continue
                for items in search_pages(
                    client,
                    str(region.fias_guid),
                    house_type,
                    max_pages=options["max_pages"],
                    pause=options["sleep"],
                ):
                    stats["pages"] += 1
                    stats["found"] += len(items)
                    for item in items:
                        try:
                            house, created = ensure_search_house(
                                region=region,
                                normalized=normalize_search_item(item, region_name=region.name),
                            )
                            stats["houses_created"] += int(created)
                            if house.detail_fetched_at is not None:
                                stats["skipped"] += 1
                                continue
                        except (ValidationError, ValueError, TypeError):
                            stats["errors"] += 1
                            self.stderr.write(
                                "Поисковая запись пропущена: некорректный GUID или регион"
                            )
                            continue
                        try:
                            result = fetch_missing_detail(
                                client, house, type_code=str(house_type["code"])
                            )
                            stats["details_fetched"] += int(result.fetched)
                            stats["organizations_created"] += int(result.organization_created)
                            stats["management_created"] += int(result.management_created)
                        except Exception:
                            stats["detail_errors"] += 1
                            stats["errors"] += 1
                            self.stderr.write("Карточка не сохранена; повтор при следующем запуске")
                        if options["sleep"]:
                            time.sleep(options["sleep"])
        self.stdout.write("; ".join(f"{key}={value}" for key, value in stats.items()))
        if stats["errors"]:
            raise CommandError(
                "Синхронизация завершена с ошибками; подробные карточки можно повторить"
            )
