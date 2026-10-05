from decimal import Decimal

from django.test import SimpleTestCase

from registry.models import ManagementMethod
from registry.services.api import GISHousingClient, build_search_payload
from registry.services.mapping import normalize_detail, normalize_management_method


class MappingTests(SimpleTestCase):
    def test_management_method_mapping(self):
        self.assertEqual(
            normalize_management_method("Управляющая организация"), ManagementMethod.UO
        )
        self.assertEqual(normalize_management_method("ТСЖ"), ManagementMethod.HOA_COOPERATIVE)
        self.assertEqual(normalize_management_method("ЖСК"), ManagementMethod.HOA_COOPERATIVE)
        self.assertEqual(
            normalize_management_method("Непосредственное управление"),
            ManagementMethod.DIRECT,
        )

    def test_mkd_detail_from_observed_response(self):
        payload = {
            "guid": "7c5711a3-17bc-4c84-8eb8-37f651970b56",
            "status": "APPROVED",
            "approved": True,
            "address": {
                "formattedAddress": "150048, обл Ярославская, г Ярославль, пер Герцена, д. 6, к. 2",
                "region": {"formalName": "Ярославская"},
                "city": {"formalName": "Ярославль"},
                "street": {"formalName": "Герцена"},
                "house": {
                    "guid": "f6616c57-63f5-4283-9525-221c4fa1f04b",
                    "houseGuid": "59cefc1b-d34c-48be-900e-5129ea4d9e53",
                    "postalCode": "150048",
                },
            },
            "oktmo": {"code": "78701000001", "name": "г Ярославль"},
            "houseType": {"code": "1", "houseTypeName": "Многоквартирный"},
            "houseManagementType": {"code": "2", "houseManagementTypeName": "ТСЖ"},
            "managementOrganization": {
                "guid": "a46e7d91-8970-4fdc-a37f-d517260cbe6f",
                "fullName": "ТОВАРИЩЕСТВО СОБСТВЕННИКОВ ЖИЛЬЯ ПЕРЕУЛОК ГЕРЦЕНА",
                "shortName": "ТСЖ ПЕРЕУЛОК ГЕРЦЕНА",
                "ogrn": "1037601007531",
            },
            "managementContractDate": "20.11.2003",
            "totalSquare": "2624.8",
            "residentialSquare": "2561.7",
            "buildingYear": "2003",
            "operationYear": 2003,
            "cadastreNumber": "76:23:010101:5662",
        }

        normalized, organization = normalize_detail(payload)

        self.assertEqual(normalized["management_method"], ManagementMethod.HOA_COOPERATIVE)
        self.assertEqual(normalized["total_square"], Decimal("2624.8"))
        self.assertEqual(normalized["fias_house_guid"], "59cefc1b-d34c-48be-900e-5129ea4d9e53")
        self.assertEqual(organization["ogrn"], "1037601007531")

    def test_search_count_only_on_first_page_is_configurable(self):
        first = build_search_payload("region", calc_count=True)
        next_page = build_search_payload("region", calc_count=False)
        self.assertTrue(first["calcCount"])
        self.assertFalse(next_page["calcCount"])

    def test_detail_endpoint_contains_type_and_guid(self):
        client = object.__new__(GISHousingClient)
        calls = {}

        def fake_request(method, path, **kwargs):
            calls.update(method=method, path=path)
            return {}

        client._request = fake_request
        client.house_detail(type_code="1", guid="abc")
        self.assertEqual(
            calls,
            {
                "method": "GET",
                "path": "/homemanagement/api/rest/services/houses/public/1/abc",
            },
        )
