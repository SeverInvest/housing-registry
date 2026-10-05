from __future__ import annotations

import time
from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from registry.models import House, ImportRun, ImportSource, ImportStatus, Region
from registry.services.api import GISHousingClient
from registry.services.mapping import normalize_detail
from registry.services.persistence import persist_house


class Command(BaseCommand):
    help = "Загружает публичные карточки домов ГИС ЖКХ"

    def add_arguments(self, parser):
        parser.add_argument("--region-code", help="Ограничить загрузку одним регионом")
        parser.add_argument(
            "--mode",
            choices=("pending", "missing", "stale", "all"),
            default="pending",
            help="Какие карточки обновлять",
        )
        parser.add_argument("--stale-days", type=int, default=90)
        parser.add_argument("--limit", type=int)
        parser.add_argument(
            "--sleep", type=float, default=0.25, help="Пауза между запросами, секунд"
        )
        parser.add_argument(
            "--guid",
            action="append",
            dest="guids",
            help="GUID конкретного дома; можно повторять",
        )

    def handle(self, *args, **options):
        if options["stale_days"] < 0:
            raise CommandError("--stale-days не может быть отрицательным")

        queryset = House.objects.filter(active=True, house_type_code="1").order_by("id")
        region = None
        if options.get("region_code"):
            region = Region.objects.filter(code=options["region_code"]).first()
            if region is None:
                raise CommandError(f"Регион с кодом {options['region_code']} не найден")
            queryset = queryset.filter(region=region)
        if options.get("guids"):
            queryset = queryset.filter(gis_guid__in=options["guids"])
        elif options["mode"] == "pending":
            queryset = queryset.filter(needs_detail_refresh=True)
        elif options["mode"] == "missing":
            queryset = queryset.filter(detail_fetched_at__isnull=True)
        elif options["mode"] == "stale":
            threshold = timezone.now() - timedelta(days=options["stale_days"])
            queryset = queryset.filter(detail_fetched_at__lt=threshold)

        if options["limit"]:
            queryset = queryset[: options["limit"]]
        house_ids = list(queryset.values_list("id", flat=True))
        run = ImportRun.objects.create(
            region=region,
            source=ImportSource.GIS_DETAIL,
            parameters={
                "mode": options["mode"],
                "stale_days": options["stale_days"],
                "limit": options["limit"],
                "guids": options.get("guids"),
                "region_code": region.code if region else None,
            },
            total_expected=len(house_ids),
        )
        counters = {
            "created": 0,
            "updated": 0,
            "unchanged": 0,
            "errors": 0,
            "processed": 0,
        }
        error_messages: list[str] = []

        try:
            with GISHousingClient() as client:
                for position, house in enumerate(
                    House.objects.filter(id__in=house_ids).order_by("id"), start=1
                ):
                    try:
                        payload = client.house_detail(
                            type_code=house.house_type_code, guid=str(house.gis_guid)
                        )
                        normalized, organization = normalize_detail(payload)
                        _, outcome = persist_house(
                            region=house.region,
                            normalized=normalized,
                            organization_data=organization,
                            raw_payload=payload,
                            source=ImportSource.GIS_DETAIL,
                            run=run,
                        )
                        counters[outcome] += 1
                    except Exception as exc:  # retain the rest of the batch
                        counters["errors"] += 1
                        if len(error_messages) < 50:
                            error_messages.append(f"{house.gis_guid}: {exc}")
                    finally:
                        counters["processed"] += 1

                    if position % 100 == 0 or position == len(house_ids):
                        self.stdout.write(f"Карточки: {position}/{len(house_ids)}")
                    if position < len(house_ids) and options["sleep"]:
                        time.sleep(options["sleep"])

            run.status = (
                ImportStatus.COMPLETED_WITH_ERRORS if counters["errors"] else ImportStatus.COMPLETED
            )
            run.finished_at = timezone.now()
            run.processed = counters["processed"]
            run.created_count = counters["created"]
            run.updated_count = counters["updated"]
            run.unchanged_count = counters["unchanged"]
            run.error_count = counters["errors"]
            run.message = "\n".join(error_messages)
            run.save()
            self.stdout.write(self.style.SUCCESS("Синхронизация карточек завершена"))
        except Exception as exc:
            run.status = ImportStatus.FAILED
            run.finished_at = timezone.now()
            run.message = str(exc)
            run.error_count = counters["errors"] + 1
            run.processed = counters["processed"]
            run.save()
            raise
