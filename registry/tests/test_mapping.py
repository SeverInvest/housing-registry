from decimal import Decimal

from django.test import SimpleTestCase

from registry.models import ManagementBasis, ManagementMethod
from registry.services.mapping import build_address, normalize_detail, normalize_management_method


class MappingTests(SimpleTestCase):
    def test_address_order_and_whitespace(self):
        fields = {
            "postal_code": " 123456 ",
            "district": " Район  Северный ",
            "city": "Город",
            "settlement": "Посёлок",
            "planning_structure_element": "квартал 1",
            "street": "ул. Мира",
            "building_number": "14 корпус 2 литер А",
        }
        self.assertEqual(
            build_address(fields, "Область"),
            "123456, Область, Район Северный, Город, квартал 1, ул. Мира, 14 корпус 2 литер А",
        )
        self.assertEqual(build_address({"settlement": "Посёлок"}, ""), "Посёлок")

    def test_building_number_remains_one_string(self):
        for number in ["14", "14 корпус 2", "14 строение 3", "14 литер А", "19/13"]:
            with self.subTest(number=number):
                house, _, _ = normalize_detail({"address": {"house": {"buildingNumber": number}}})
                self.assertEqual(house["building_number"], number)
                self.assertEqual(house["address"], number)

    def test_methods_are_distinct(self):
        expected = {
            "УО": ManagementMethod.MANAGEMENT_COMPANY,
            "Управляющая организация": ManagementMethod.MANAGEMENT_COMPANY,
            "ТСЖ": ManagementMethod.HOA_TSN,
            "ТСН": ManagementMethod.HOA_TSN,
            "ЖСК": ManagementMethod.HOUSING_COOPERATIVE,
            "ЖК": ManagementMethod.HOUSING_COOPERATIVE,
            "Непосредственное управление": ManagementMethod.DIRECT,
            "Способ управления не выбран": ManagementMethod.NOT_SELECTED,
            "Иной способ": ManagementMethod.OTHER,
        }
        for source, value in expected.items():
            self.assertEqual(normalize_management_method(source), value)

    def test_unknown_method_logged_without_response_value(self):
        with self.assertLogs("registry.services.mapping", level="WARNING") as logs:
            result = normalize_management_method("неизвестное значение источника")
        self.assertEqual(result, ManagementMethod.UNKNOWN)
        self.assertNotIn("значение источника", " ".join(logs.output))

    def test_areas_have_separate_meaning(self):
        house, _, management = normalize_detail(
            {
                "totalSquare": "1250,1234",
                "residentialSquare": "1000.0001",
                "residentialPremiseActualCount": 0,
            }
        )
        self.assertEqual(house["area_total"], Decimal("1250.1234"))
        self.assertEqual(house["area_residential"], Decimal("1000.0001"))
        self.assertNotIn("residential_premises_area", house)
        self.assertNotIn("non_residential_premises_area", house)
        self.assertEqual(house["residential_premises_count"], 0)
        self.assertEqual(management["management_basis"], ManagementBasis.UNKNOWN)

    def test_direct_management_discards_organization(self):
        _, organization, management = normalize_detail(
            {
                "houseManagementType": {"houseManagementTypeName": "Непосредственное управление"},
                "managementOrganization": {"fullName": "Не относится к прямому управлению"},
            }
        )
        self.assertIsNone(organization)
        self.assertEqual(management["management_method"], ManagementMethod.DIRECT)
