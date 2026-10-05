from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from registry.models import Region


class ConfigureRegionCommandTests(TestCase):
    def test_region_can_be_created_before_fias_configuration(self):
        output = StringIO()
        call_command("configure_region", code="76", name="Тестовый регион", stdout=output)
        region = Region.objects.get(code="76")
        self.assertIsNone(region.fias_guid)
        self.assertTrue(region.sync_enabled)
        self.assertIn("создан", output.getvalue())

    def test_region_can_be_configured_with_fias_guid(self):
        call_command(
            "configure_region",
            code="76",
            name="Тестовый регион",
            fias_guid="00000000-0000-4000-8000-000000000001",
            stdout=StringIO(),
        )
        self.assertIsNotNone(Region.objects.get(code="76").fias_guid)
