import uuid
from io import StringIO
from unittest.mock import Mock, patch

import httpx
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, TestCase

from registry.models import House, HouseManagement, Region
from registry.services.api import MKD_HOUSE_TYPE_REF, GISHousingAPIError, GISHousingClient
from registry.services.synchronization import fetch_missing_detail, search_pages


class PaginationTests(SimpleTestCase):
    def test_pagination_uses_100_and_calculates_count_only_once(self):
        client = Mock()
        client.search_houses.side_effect = [
            {"total": 101, "items": [{}] * 100},
            {"items": [{}]},
        ]
        pages = list(search_pages(client, "region", MKD_HOUSE_TYPE_REF))
        self.assertEqual([len(p) for p in pages], [100, 1])
        calls = client.search_houses.call_args_list
        self.assertEqual([c.kwargs["page_index"] for c in calls], [0, 1])
        self.assertTrue(calls[0].kwargs["payload"]["calcCount"])
        self.assertFalse(calls[1].kwargs["payload"]["calcCount"])
        self.assertTrue(all(c.kwargs["elements_per_page"] == 100 for c in calls))

    def test_missing_total_continues_until_empty_page(self):
        client = Mock()
        client.search_houses.side_effect = [{"items": [{}]}, {"items": []}]
        self.assertEqual(len(list(search_pages(client, "region", MKD_HOUSE_TYPE_REF))), 1)
        self.assertEqual(client.search_houses.call_count, 2)

    def test_last_page_flag_stops_pagination(self):
        client = Mock()
        client.search_houses.return_value = {"items": [{}], "last": True}
        self.assertEqual(len(list(search_pages(client, "region", MKD_HOUSE_TYPE_REF))), 1)
        self.assertEqual(client.search_houses.call_count, 1)


class DetailLoadingTests(TestCase):
    def setUp(self):
        self.region = Region.objects.create(
            code="76", name="Тестовый регион", fias_guid=uuid.uuid4()
        )
        self.house = House.objects.create(region=self.region, gis_guid=uuid.uuid4())
        self.client = Mock()
        self.payload = {
            "guid": str(self.house.gis_guid),
            "houseManagementType": {"houseManagementTypeName": "Непосредственное управление"},
            "address": {"house": {"buildingNumber": "19/13"}},
        }

    def test_successful_card_is_not_requested_again(self):
        self.client.house_detail.return_value = self.payload
        self.assertTrue(fetch_missing_detail(self.client, self.house).fetched)
        self.assertFalse(fetch_missing_detail(self.client, self.house).fetched)
        self.client.house_detail.assert_called_once()
        self.assertEqual(HouseManagement.objects.count(), 1)

    def test_failed_card_is_retried_on_next_attempt(self):
        self.client.house_detail.side_effect = [
            GISHousingAPIError("Временная ошибка"),
            self.payload,
        ]
        with self.assertRaises(GISHousingAPIError):
            fetch_missing_detail(self.client, self.house)
        self.house.refresh_from_db()
        self.assertIsNone(self.house.detail_fetched_at)
        self.assertTrue(fetch_missing_detail(self.client, self.house).fetched)
        self.assertEqual(self.client.house_detail.call_count, 2)

    def test_search_command_creates_house_and_loads_detail(self):
        new_guid = str(uuid.uuid4())
        self.client.search_houses.return_value = {"total": 1, "items": [{"guid": new_guid}]}
        self.client.house_detail.return_value = {**self.payload, "guid": new_guid}
        self.client.__enter__ = Mock(return_value=self.client)
        self.client.__exit__ = Mock(return_value=False)
        with patch(
            "registry.management.commands.sync_gis_houses.GISHousingClient",
            return_value=self.client,
        ):
            call_command("sync_gis_houses", region_code="76", sleep=0, stdout=StringIO())
            call_command("sync_gis_houses", region_code="76", sleep=0, stdout=StringIO())
        house = House.objects.get(gis_guid=new_guid)
        self.assertIsNotNone(house.detail_fetched_at)
        self.assertEqual(HouseManagement.objects.filter(house=house).count(), 1)
        self.client.house_detail.assert_called_once()

    def test_search_command_skips_invalid_guid_and_processes_next_house(self):
        new_guid = str(uuid.uuid4())
        self.client.search_houses.return_value = {
            "total": 2,
            "items": [{"guid": "not-a-uuid"}, {"guid": new_guid}],
        }
        self.client.house_detail.return_value = {**self.payload, "guid": new_guid}
        self.client.__enter__ = Mock(return_value=self.client)
        self.client.__exit__ = Mock(return_value=False)
        stdout = StringIO()
        stderr = StringIO()
        with patch(
            "registry.management.commands.sync_gis_houses.GISHousingClient",
            return_value=self.client,
        ):
            # Команда сообщает об учтённых ошибках после обработки всех записей.
            with self.assertRaisesMessage(CommandError, "Синхронизация завершена с ошибками"):
                call_command(
                    "sync_gis_houses", region_code="76", sleep=0, stdout=stdout, stderr=stderr
                )
        stats = dict(item.split("=", 1) for item in stdout.getvalue().strip().split("; "))
        self.assertEqual(stats["found"], "2")
        self.assertEqual(stats["errors"], "1")
        self.assertEqual(stats["houses_created"], "1")
        self.assertEqual(stats["details_fetched"], "1")
        self.assertEqual(stats["detail_errors"], "0")
        self.assertIn("Поисковая запись пропущена: некорректный GUID или регион", stderr.getvalue())
        self.assertEqual(House.objects.count(), 2)
        house = House.objects.get(gis_guid=new_guid)
        self.assertIsNotNone(house.detail_fetched_at)
        self.assertEqual(HouseManagement.objects.filter(house=house).count(), 1)
        self.client.house_detail.assert_called_once_with(type_code="1", guid=new_guid)

    def test_discovery_does_not_remove_previously_loaded_house(self):
        self.client.search_houses.return_value = {"total": 0, "items": []}
        self.client.__enter__ = Mock(return_value=self.client)
        self.client.__exit__ = Mock(return_value=False)
        with patch(
            "registry.management.commands.sync_gis_houses.GISHousingClient",
            return_value=self.client,
        ):
            call_command("sync_gis_houses", region_code="76", sleep=0, stdout=StringIO())
        self.assertTrue(House.objects.filter(pk=self.house.pk).exists())


class HTTPRetryTests(SimpleTestCase):
    def test_normal_4xx_is_not_retried(self):
        transport = Mock(return_value=httpx.Response(403))
        with GISHousingClient(base_url="https://example.test", max_retries=2) as client:
            client.client.close()
            client.client = httpx.Client(
                base_url="https://example.test", transport=httpx.MockTransport(transport)
            )
            with self.assertRaises(GISHousingAPIError):
                client.house_detail(type_code="1", guid="test")
        self.assertEqual(transport.call_count, 1)

    def test_temporary_error_is_retried(self):
        transport = Mock(
            side_effect=[httpx.Response(429), httpx.Response(200, json={"guid": "test"})]
        )
        with GISHousingClient(base_url="https://example.test", max_retries=2) as client:
            client.client.close()
            client.client = httpx.Client(
                base_url="https://example.test", transport=httpx.MockTransport(transport)
            )
            with patch("registry.services.api.time.sleep"):
                self.assertEqual(client.house_detail(type_code="1", guid="test"), {"guid": "test"})
        self.assertEqual(transport.call_count, 2)
