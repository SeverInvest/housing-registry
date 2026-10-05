from __future__ import annotations

import json
import math
import time
from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db.models import F
from django.utils import timezone

from registry.models import (
    House,
    ImportRun,
    ImportSource,
    ImportStatus,
    ManagementMethod,
    Region,
)
from registry.services.api import (
    MKD_HOUSE_TYPE_REF,
    GISHousingClient,
    build_search_payload,
)
from registry.services.mapping import normalize_search_item
from registry.services.persistence import persist_house


class Command(BaseCommand):
    help = "Загружает постраничный перечень домов из публичного поиска ГИС ЖКХ"

    def add_arguments(self, parser):
        parser.add_argument("--region-code", default=settings.GIS_REGION_CODE)
        parser.add_argument("--region-guid", default=settings.GIS_REGION_GUID)
        parser.add_argument("--page-size", type=int, default=100)
        parser.add_argument("--max-pages", type=int)
        parser.add_argument(
            "--sleep", type=float, default=0.25, help="Пауза между запросами, секунд"
        )
        parser.add_argument(
            "--house-type-ref-json",
            default=json.dumps(MKD_HOUSE_TYPE_REF, ensure_ascii=False),
            help="JSON объекта справочника типа дома; по умолчанию МКД",
        )
        parser.add_argument(
            "--management-type-ref-json",
            help="JSON объекта справочника способа управления из HAR; если не задан — все способы",
        )
        parser.add_argument(
            "--forced-management-method",
            choices=[choice for choice, _ in ManagementMethod.choices],
            help="Записать способ управления из контекста фильтрованного запроса",
        )
        parser.add_argument(
            "--authoritative",
            action="store_true",
            help="Пометить отсутствующие в полном результате МКД как неактуальные",
        )
        parser.add_argument(
            "--deactivate-after-misses",
            type=int,
            default=2,
            help="Число полных успешных запусков без дома до деактивации",
        )

    def handle(self, *args, **options):
        region = self._resolve_region(
            code=options.get("region_code"), guid=options.get("region_guid")
        )
        region_guid = str(region.fias_guid)
        page_size = options["page_size"]
        if not 1 <= page_size <= 1000:
            raise CommandError("--page-size должен быть от 1 до 1000")
        if options["deactivate_after_misses"] < 1:
            raise CommandError("--deactivate-after-misses должен быть не меньше 1")

        house_type_ref = self._parse_ref(options["house_type_ref_json"], "--house-type-ref-json")
        management_type_ref = self._parse_ref(
            options.get("management_type_ref_json"), "--management-type-ref-json"
        )
        if options["authoritative"] and (management_type_ref or options["max_pages"]):
            raise CommandError(
                "--authoritative нельзя сочетать с фильтром способа управления или --max-pages"
            )

        parameters = {
            "region_code": region.code,
            "region_guid": region_guid,
            "page_size": page_size,
            "max_pages": options["max_pages"],
            "house_type_ref": house_type_ref,
            "management_type_ref": management_type_ref,
            "forced_management_method": options.get("forced_management_method"),
            "authoritative": options["authoritative"],
            "deactivate_after_misses": options["deactivate_after_misses"],
        }
        run = ImportRun.objects.create(
            region=region,
            source=ImportSource.GIS_SEARCH,
            parameters=parameters,
        )
        seen_guids: set[str] = set()
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
                first_payload = build_search_payload(
                    region_guid,
                    calc_count=True,
                    house_type_refs=[house_type_ref] if house_type_ref else None,
                    management_type_refs=[management_type_ref] if management_type_ref else None,
                )
                first_page = client.search_houses(
                    page_index=0, elements_per_page=page_size, payload=first_payload
                )
                total = int(first_page.get("total") or 0)
                first_items = first_page.get("items") or []
                if options["authoritative"] and total == 0:
                    raise CommandError(
                        "Авторитетная синхронизация вернула 0 объектов; деактивация отменена"
                    )
                if total > page_size and len(first_items) < page_size:
                    raise CommandError(
                        "Сервер вернул только "
                        f"{len(first_items)} записей при page-size={page_size}. "
                        "Укажите фактически поддерживаемый размер страницы, "
                        "чтобы не пропустить дома."
                    )
                pages = max(1, math.ceil(total / page_size)) if total else 1
                if options["max_pages"]:
                    pages = min(pages, options["max_pages"])
                run.total_expected = total
                run.save(update_fields=("total_expected",))
                self.stdout.write(f"Найдено объектов: {total}; страниц к загрузке: {pages}")

                for page_index in range(pages):
                    if page_index == 0:
                        items = first_items
                    else:
                        payload = build_search_payload(
                            region_guid,
                            calc_count=False,
                            house_type_refs=[house_type_ref] if house_type_ref else None,
                            management_type_refs=[management_type_ref]
                            if management_type_ref
                            else None,
                        )
                        response = client.search_houses(
                            page_index=page_index,
                            elements_per_page=page_size,
                            payload=payload,
                        )
                        items = response.get("items") or []

                    for item in items:
                        try:
                            normalized, organization = normalize_search_item(
                                item,
                                forced_management_method=options.get("forced_management_method"),
                            )
                            house, outcome = persist_house(
                                region=region,
                                normalized=normalized,
                                organization_data=organization,
                                raw_payload=item,
                                source=ImportSource.GIS_SEARCH,
                                run=run,
                            )
                            seen_guids.add(str(house.gis_guid))
                            counters[outcome] += 1
                        except Exception as exc:  # continue the batch, but retain diagnostics
                            counters["errors"] += 1
                            if len(error_messages) < 50:
                                error_messages.append(f"{item.get('guid')}: {exc}")
                        finally:
                            counters["processed"] += 1

                    self.stdout.write(
                        f"Страница {page_index + 1}/{pages}: {len(items)} записей; "
                        f"обработано {counters['processed']}"
                    )
                    if page_index + 1 < pages and options["sleep"]:
                        time.sleep(options["sleep"])

            if options["authoritative"]:
                if counters["errors"] or len(seen_guids) != run.total_expected:
                    self.stderr.write(
                        self.style.WARNING(
                            "Деактивация пропущена: обработка завершилась с ошибками "
                            "или число уникальных GUID не совпало с total"
                        )
                    )
                else:
                    missing = House.objects.filter(
                        region=region, active=True, house_type_code="1"
                    ).exclude(gis_guid__in=seen_guids)
                    missing.update(
                        consecutive_missing_runs=F("consecutive_missing_runs") + 1,
                        last_missing_at=timezone.now(),
                    )
                    House.objects.filter(
                        region=region,
                        active=True,
                        house_type_code="1",
                        consecutive_missing_runs__gte=options["deactivate_after_misses"],
                    ).update(active=False, needs_detail_refresh=False)

            self._finish_run(run, counters, error_messages)
            self.stdout.write(self.style.SUCCESS("Синхронизация поискового перечня завершена"))
        except Exception as exc:
            run.status = ImportStatus.FAILED
            run.finished_at = timezone.now()
            run.message = str(exc)
            run.error_count = counters["errors"] + 1
            run.processed = counters["processed"]
            run.save()
            raise

    @staticmethod
    def _resolve_region(*, code: str | None, guid: str | None) -> Region:
        code = (code or "").strip()
        guid = (guid or "").strip()
        if not code and not guid:
            raise CommandError(
                "Укажите --region-code или --region-guid. "
                "Регион должен быть предварительно создан в админке."
            )

        queryset = Region.objects.filter(sync_enabled=True)
        region = (
            queryset.filter(code=code).first() if code else queryset.filter(fias_guid=guid).first()
        )
        if region is None:
            value = code or guid
            raise CommandError(
                f"Активный регион {value} не найден. Создайте его в разделе «Регионы» админки."
            )
        if guid and str(region.fias_guid) != guid:
            raise CommandError(
                f"Код {region.code} относится к GUID {region.fias_guid}, а передан {guid}"
            )
        return region

    @staticmethod
    def _parse_ref(raw: str | None, option_name: str) -> dict[str, Any] | None:
        if not raw or raw.lower() == "null":
            return None
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise CommandError(f"Некорректный JSON в {option_name}: {exc}") from exc
        if not isinstance(value, dict):
            raise CommandError(f"{option_name} должен содержать JSON-объект")
        return value

    @staticmethod
    def _finish_run(run, counters, error_messages):
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
