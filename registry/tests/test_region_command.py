from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from registry.models import Region


class ConfigureRegionCommandTests(TestCase):
    def test_command_creates_region(self):
        output = StringIO()

        call_command(
            "configure_region",
            code="76",
            name="Ярославская область",
            fias_guid="a84b2ef4-db03-474b-b552-6229e801ae9b",
            federal_district="Центральный федеральный округ",
            stdout=output,
        )

        region = Region.objects.get(code="76")
        self.assertEqual(region.name, "Ярославская область")
        self.assertTrue(region.sync_enabled)
        self.assertIn("создан", output.getvalue())
