import uuid
from datetime import date

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.test import TestCase

from registry.models import (
    House,
    HouseManagement,
    ManagementBasis,
    ManagementMethod,
    ManagementSource,
    Organization,
    Region,
)
from registry.services.persistence import (
    ensure_search_house,
    persist_detail,
    update_management,
    upsert_organization,
)


class PersistenceTests(TestCase):
    def setUp(self):
        self.region = Region.objects.create(code="76", name="Тестовый регион")
        self.house = House.objects.create(
            region=self.region, gis_guid=uuid.uuid4(), address="Дом 1"
        )
        self.normalized = {
            "gis_guid": str(self.house.gis_guid),
            "address": "Дом 1",
            "area_total": 100,
        }
        self.management = {"management_method": ManagementMethod.DIRECT}

    def period(self, **kwargs):
        return update_management(
            house=self.house,
            organization=None,
            source=ManagementSource.GIS_DETAIL,
            management_method=ManagementMethod.DIRECT,
            **kwargs,
        )[0]

    def test_search_repeat_does_not_create_or_overwrite_house(self):
        for _ in range(2):
            house, created = ensure_search_house(
                region=self.region,
                normalized={"gis_guid": self.house.gis_guid, "address": "Другой"},
            )
            self.assertFalse(created)
            self.assertEqual(house.address, "Дом 1")
        self.assertEqual(House.objects.count(), 1)

    def test_missing_guid_is_rejected_without_writes(self):
        with self.assertRaises(ValueError):
            ensure_search_house(region=self.region, normalized={"address": "Новый"})
        self.assertEqual(House.objects.count(), 1)

    def test_other_region_cannot_take_existing_house(self):
        other = Region.objects.create(code="77", name="Другой регион")
        with self.assertRaises(ValueError):
            ensure_search_house(region=other, normalized=self.normalized)

    def test_detail_is_saved_once(self):
        first = persist_detail(
            house=self.house,
            normalized=self.normalized,
            organization_data=None,
            management=self.management,
        )
        second = persist_detail(
            house=self.house,
            normalized={**self.normalized, "area_total": 200},
            organization_data=None,
            management=self.management,
        )
        self.assertTrue(first.fetched)
        self.assertFalse(second.fetched)
        self.house.refresh_from_db()
        self.assertEqual(self.house.area_total, 100)
        self.assertIsNotNone(self.house.detail_fetched_at)
        self.assertEqual(HouseManagement.objects.count(), 1)

    def test_detail_failure_rolls_back_house_organization_and_timestamp(self):
        with self.assertRaises(ValidationError):
            persist_detail(
                house=self.house,
                normalized=self.normalized,
                organization_data={"full_name": "Тестовая организация", "ogrn": "1000000000001"},
                management={"management_method": "invalid"},
            )
        self.house.refresh_from_db()
        self.assertIsNone(self.house.detail_fetched_at)
        self.assertIsNone(self.house.area_total)
        self.assertEqual(Organization.objects.count(), 0)
        self.assertEqual(HouseManagement.objects.count(), 0)

    def test_direct_management_without_organization(self):
        self.assertIsNone(self.period().organization_id)

    def test_management_repeat_is_idempotent(self):
        self.assertEqual(self.period().pk, self.period().pk)
        self.assertEqual(HouseManagement.objects.count(), 1)

    def test_management_change_closes_previous_period(self):
        first = self.period(date_start=date(2020, 1, 1))
        organization = Organization.objects.create(full_name="Тестовая УО")
        current, created = update_management(
            house=self.house,
            organization=organization,
            management_method=ManagementMethod.MANAGEMENT_COMPANY,
            source=ManagementSource.LICENSE_REGISTRY,
            date_start=date(2026, 1, 1),
            previous_finish_date=date(2025, 12, 31),
        )
        first.refresh_from_db()
        self.assertTrue(created)
        self.assertFalse(first.is_active)
        self.assertEqual(first.date_finish, date(2025, 12, 31))
        self.assertTrue(current.is_active)
        self.assertEqual(current.management_basis, ManagementBasis.UNKNOWN)
        self.assertEqual(HouseManagement.objects.filter(is_active=True).count(), 1)

    def test_invalid_replacement_rolls_back_previous_period(self):
        first = self.period()
        with self.assertRaises(ValidationError):
            update_management(
                house=self.house,
                organization=None,
                management_method="invalid",
                source=ManagementSource.MANUAL,
            )
        first.refresh_from_db()
        self.assertTrue(first.is_active)
        self.assertEqual(HouseManagement.objects.count(), 1)

    def test_database_rejects_two_active_periods(self):
        self.period()
        with self.assertRaises(IntegrityError), transaction.atomic():
            HouseManagement.objects.create(
                house=self.house,
                management_method=ManagementMethod.DIRECT,
                source=ManagementSource.MANUAL,
            )

    def test_database_rejects_invalid_dates(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            HouseManagement.objects.create(
                house=self.house,
                source=ManagementSource.MANUAL,
                date_start=date(2026, 1, 2),
                date_finish=date(2026, 1, 1),
            )

    def test_database_rejects_organization_for_direct_management(self):
        organization = Organization.objects.create(full_name="Организация")
        with self.assertRaises(IntegrityError), transaction.atomic():
            HouseManagement.objects.create(
                house=self.house,
                organization=organization,
                management_method=ManagementMethod.DIRECT,
                source=ManagementSource.MANUAL,
            )

    def test_management_history_protects_organization(self):
        organization = Organization.objects.create(full_name="Организация")
        update_management(
            house=self.house,
            organization=organization,
            management_method=ManagementMethod.MANAGEMENT_COMPANY,
            source=ManagementSource.MANUAL,
        )
        with self.assertRaises(ProtectedError):
            organization.delete()


class OrganizationTests(TestCase):
    def test_ogrn_has_priority_over_guid(self):
        guid = uuid.uuid4()
        existing = Organization.objects.create(full_name="Организация", ogrn="1000000000001")
        result = upsert_organization(
            {
                "ogrn": existing.ogrn,
                "gis_guid": guid,
                "full_name": "Обновлённое имя",
            }
        )
        self.assertEqual(result.pk, existing.pk)
        self.assertEqual(result.gis_guid, guid)
        self.assertEqual(Organization.objects.count(), 1)

    def test_guid_matching(self):
        guid = uuid.uuid4()
        existing = Organization.objects.create(full_name="Организация", gis_guid=guid)
        result = upsert_organization({"gis_guid": guid, "full_name": "Обновлённое имя"})
        self.assertEqual(result.pk, existing.pk)

    def test_exact_inn_kpp_matching(self):
        existing = Organization.objects.create(
            full_name="Организация", inn="1000000000", kpp="100001001"
        )
        result = upsert_organization(
            {
                "inn": existing.inn,
                "kpp": existing.kpp,
                "full_name": "Обновлённое имя",
            }
        )
        self.assertEqual(result.pk, existing.pk)

    def test_same_name_or_inn_alone_does_not_merge_organizations(self):
        first = upsert_organization({"full_name": "Одинаковое имя", "inn": "1000000000"})
        second = upsert_organization({"full_name": "Одинаковое имя", "inn": "1000000000"})
        self.assertNotEqual(first.pk, second.pk)

    def test_database_enforces_unique_present_ogrn(self):
        Organization.objects.create(full_name="Первая", ogrn="1000000000001")
        with self.assertRaises(IntegrityError), transaction.atomic():
            Organization.objects.create(full_name="Вторая", ogrn="1000000000001")
        Organization.objects.create(full_name="Без ОГРН 1")
        Organization.objects.create(full_name="Без ОГРН 2")
