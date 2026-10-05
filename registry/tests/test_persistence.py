from django.test import TestCase

from registry.models import House, HouseVersion, ImportRun, ImportSource, Region
from registry.services.persistence import persist_house


class PersistenceTests(TestCase):
    def setUp(self):
        self.region = Region.objects.create(
            code="76",
            name="Ярославская область",
            fias_guid="a84b2ef4-db03-474b-b552-6229e801ae9b",
        )
        self.run = ImportRun.objects.create(region=self.region, source=ImportSource.GIS_SEARCH)
        self.normalized = {
            "gis_guid": "7c5711a3-17bc-4c84-8eb8-37f651970b56",
            "formatted_address": "Тестовый дом",
            "house_type_code": "1",
            "house_type_name": "Многоквартирный",
            "approved": True,
        }

    def test_unchanged_record_does_not_create_duplicate_version(self):
        persist_house(
            region=self.region,
            normalized=self.normalized,
            organization_data=None,
            raw_payload={"guid": self.normalized["gis_guid"]},
            source=ImportSource.GIS_SEARCH,
            run=self.run,
        )
        persist_house(
            region=self.region,
            normalized=self.normalized,
            organization_data=None,
            raw_payload={"guid": self.normalized["gis_guid"]},
            source=ImportSource.GIS_SEARCH,
            run=self.run,
        )

        self.assertEqual(House.objects.count(), 1)
        self.assertEqual(HouseVersion.objects.count(), 1)

    def test_changed_record_marks_detail_refresh(self):
        house, _ = persist_house(
            region=self.region,
            normalized=self.normalized,
            organization_data=None,
            raw_payload={},
            source=ImportSource.GIS_SEARCH,
            run=self.run,
        )
        house.needs_detail_refresh = False
        house.save(update_fields=("needs_detail_refresh",))
        changed = {**self.normalized, "cadastre_number": "76:00:000000:1"}

        house, outcome = persist_house(
            region=self.region,
            normalized=changed,
            organization_data=None,
            raw_payload={},
            source=ImportSource.GIS_SEARCH,
            run=self.run,
        )

        self.assertEqual(outcome, "updated")
        self.assertTrue(house.needs_detail_refresh)
        self.assertEqual(HouseVersion.objects.count(), 2)

    def test_sparse_search_does_not_erase_detail_values(self):
        detail_run = ImportRun.objects.create(region=self.region, source=ImportSource.GIS_DETAIL)
        detail = {
            **self.normalized,
            "management_method": "hoa_cooperative",
            "total_square": "2624.8",
        }
        house, _ = persist_house(
            region=self.region,
            normalized=detail,
            organization_data=None,
            raw_payload={},
            source=ImportSource.GIS_DETAIL,
            run=detail_run,
        )
        sparse_search = {**self.normalized, "residential_premise_count": None}

        house, _ = persist_house(
            region=self.region,
            normalized=sparse_search,
            organization_data=None,
            raw_payload={},
            source=ImportSource.GIS_SEARCH,
            run=self.run,
        )

        house.refresh_from_db()
        self.assertEqual(house.management_method, "hoa_cooperative")
        self.assertEqual(str(house.total_square), "2624.8000")

    def test_house_cannot_silently_move_to_another_region(self):
        persist_house(
            region=self.region,
            normalized=self.normalized,
            organization_data=None,
            raw_payload={},
            source=ImportSource.GIS_SEARCH,
            run=self.run,
        )
        other_region = Region.objects.create(
            code="77",
            name="Москва",
            fias_guid="0c2edb78-9ba5-4db8-8cd7-60a6ac8c22f6",
        )

        with self.assertRaisesMessage(ValueError, "уже относится к региону"):
            persist_house(
                region=other_region,
                normalized=self.normalized,
                organization_data=None,
                raw_payload={},
                source=ImportSource.GIS_SEARCH,
                run=self.run,
            )
