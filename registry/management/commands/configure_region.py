from __future__ import annotations

import uuid

from django.core.management.base import BaseCommand, CommandError

from registry.models import Region


class Command(BaseCommand):
    help = "Создаёт или обновляет регион, используемый при синхронизации ГИС ЖКХ"

    def add_arguments(self, parser):
        parser.add_argument("--code", required=True, help="Код субъекта РФ, например 76")
        parser.add_argument("--name", required=True, help="Наименование субъекта РФ")
        parser.add_argument("--fias-guid", help="GUID субъекта РФ по ФИАС")
        parser.add_argument(
            "--disable",
            action="store_true",
            help="Создать регион с выключенной синхронизацией",
        )

    def handle(self, *args, **options):
        code = options["code"].strip()
        if not code.isdigit() or not 1 <= len(code) <= 3:
            raise CommandError("--code должен содержать от одной до трёх цифр")
        try:
            fias_guid = uuid.UUID(options["fias_guid"]) if options["fias_guid"] else None
        except (ValueError, TypeError, AttributeError) as exc:
            raise CommandError("--fias-guid должен быть корректным UUID") from exc

        region, created = Region.objects.update_or_create(
            code=code,
            defaults={
                "name": options["name"].strip(),
                "fias_guid": fias_guid,
                "sync_enabled": not options["disable"],
            },
        )
        action = "создан" if created else "обновлён"
        self.stdout.write(self.style.SUCCESS(f"Регион {region} {action}"))
