from __future__ import annotations

import time

from django.core.management.base import BaseCommand, CommandError

from registry.models import House
from registry.services.api import MKD_HOUSE_TYPE_REF, GISHousingClient
from registry.services.synchronization import fetch_missing_detail


class Command(BaseCommand):
    help = "Повторяет загрузку карточек только при detail_fetched_at=NULL"

    def add_arguments(self, parser):
        parser.add_argument("--region-code")
        parser.add_argument("--guid", action="append", dest="guids")
        parser.add_argument("--limit", type=int)
        parser.add_argument("--sleep", type=float, default=0.25)
        parser.add_argument("--type-code", default=MKD_HOUSE_TYPE_REF["code"])

    def handle(self, *args, **options):
        if options["sleep"] < 0 or (options["limit"] is not None and options["limit"] < 1):
            raise CommandError("Пауза должна быть неотрицательной; limit должен быть положительным")
        houses = (
            House.objects.filter(detail_fetched_at__isnull=True, region__sync_enabled=True)
            .select_related("region")
            .order_by("id")
        )
        if options["region_code"]:
            houses = houses.filter(region__code=options["region_code"])
        if options["guids"]:
            houses = houses.filter(gis_guid__in=options["guids"])
        if options["limit"]:
            houses = houses[: options["limit"]]
        fetched = errors = organizations = periods = 0
        with GISHousingClient() as client:
            for house in houses:
                try:
                    result = fetch_missing_detail(client, house, type_code=options["type_code"])
                    fetched += int(result.fetched)
                    organizations += int(result.organization_created)
                    periods += int(result.management_created)
                except Exception:
                    errors += 1
                    self.stderr.write("Карточка не сохранена; повтор при следующем запуске")
                if options["sleep"]:
                    time.sleep(options["sleep"])
        self.stdout.write(
            f"details_fetched={fetched}; organizations_created={organizations}; "
            f"management_created={periods}; errors={errors}"
        )
        if errors:
            raise CommandError("Не удалось загрузить часть подробных карточек")
