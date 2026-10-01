from decimal import Decimal

from django.db import IntegrityError
from django.test import TestCase
from rest_framework.test import APIClient

from apps.authentication.backends import generate_token
from apps.authentication.models import User
from .models import Approval, Category, Goods, StockIn, StockOut, Unit, Variety, Warning


class WarehouseFixture(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("warehouse-user", "testpass123", role="admin")
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {generate_token(self.user)}")
        self.unit = Unit.objects.create(name="件", created_by=self.user)
        self.category = Category.objects.create(name="受控器材", unit=self.unit, created_by=self.user)
        self.variety = Variety.objects.create(name="记录终端", category=self.category, created_by=self.user)
        self.goods = Goods.objects.create(
            variety=self.variety,
            name="执法记录终端",
            code="DEV-001",
            quantity=Decimal("12"),
            warning_threshold=Decimal("5"),
        )


class WarehouseModelTest(WarehouseFixture):
    def test_relationship_flags(self):
        self.assertTrue(self.unit.is_linked)
        self.assertTrue(self.category.is_linked)
        self.assertTrue(self.variety.is_in_stock)
        self.assertFalse(self.goods.is_warning)

    def test_unique_unit_name(self):
        with self.assertRaises(IntegrityError):
            Unit.objects.create(name="件", created_by=self.user)

    def test_stock_records_and_approval(self):
        inbound = StockIn.objects.create(goods=self.goods, operator=self.user, quantity=Decimal("3"))
        outbound = StockOut.objects.create(
            goods=self.goods, operator=self.user, receiver="保管员", quantity=Decimal("2")
        )
        approval = Approval.objects.create(stock_out=outbound, approver=self.user)
        self.assertEqual(inbound.goods_id, self.goods.id)
        self.assertEqual(approval.status, "pending")

    def test_warning_record(self):
        warning = Warning.objects.create(goods=self.goods, type="low_stock", message="库存不足")
        self.assertFalse(warning.is_read)
        self.assertIn("执法记录终端", str(warning))


class WarehouseAPITest(WarehouseFixture):
    def test_list_units(self):
        response = self.client.get("/api/units/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"]["total"], 1)

    def test_create_unit_and_reject_duplicate(self):
        created = self.client.post("/api/units/", {"name": "箱"}, format="json")
        duplicate = self.client.post("/api/units/", {"name": "箱"}, format="json")
        self.assertEqual(created.status_code, 200)
        self.assertEqual(duplicate.status_code, 400)

    def test_update_linked_unit(self):
        response = self.client.put(f"/api/units/{self.unit.id}/", {"name": "台"}, format="json")
        self.assertEqual(response.status_code, 200)
        self.unit.refresh_from_db()
        self.assertEqual(self.unit.name, "台")

    def test_refuse_delete_linked_unit(self):
        response = self.client.delete(f"/api/units/{self.unit.id}/")
        self.assertEqual(response.status_code, 400)
        self.assertTrue(Unit.objects.filter(pk=self.unit.id).exists())

    def test_create_category_validates_unit(self):
        ok = self.client.post("/api/categories/", {"name": "封存介质", "unit": self.unit.id}, format="json")
        bad = self.client.post("/api/categories/", {"name": "无效分类", "unit": 99999}, format="json")
        self.assertEqual(ok.status_code, 200)
        self.assertEqual(bad.status_code, 400)

    def test_create_variety_and_duplicate_boundary(self):
        ok = self.client.post("/api/varieties/", {"name": "封存硬盘", "category": self.category.id}, format="json")
        duplicate = self.client.post("/api/varieties/", {"name": "封存硬盘", "category": self.category.id}, format="json")
        self.assertEqual(ok.status_code, 200)
        self.assertEqual(duplicate.status_code, 400)

    def test_requires_authentication(self):
        anonymous = APIClient().get("/api/units/")
        self.assertEqual(anonymous.status_code, 401)


class PaginationBoundaryTest(WarehouseFixture):
    """单位/品类/品种列表共用同一套分页边界语义"""

    ENDPOINTS = ["/api/units/", "/api/categories/", "/api/varieties/"]

    def _assert_business_error(self, response):
        self.assertEqual(response.status_code, 400)
        body = response.json()
        self.assertFalse(body["success"])
        self.assertEqual(body["code"], 400)
        self.assertIsNone(body["data"])
        return body["message"]

    def test_zero_and_negative_page_rejected_on_every_endpoint(self):
        for endpoint in self.ENDPOINTS:
            for value in ("0", "-1"):
                with self.subTest(endpoint=endpoint, value=value):
                    response = self.client.get(endpoint, {"page": value})
                    self._assert_business_error(response)

    def test_non_numeric_params_rejected_on_every_endpoint(self):
        for endpoint in self.ENDPOINTS:
            for params in ({"page": "abc"}, {"page_size": "1.5"}, {"page": "0x2"}):
                with self.subTest(endpoint=endpoint, params=params):
                    self.assertEqual(self.client.get(endpoint, params).status_code, 400)

    def test_page_size_over_limit_rejected(self):
        for endpoint in self.ENDPOINTS:
            with self.subTest(endpoint=endpoint):
                self.assertEqual(
                    self.client.get(endpoint, {"page_size": "101"}).status_code, 400
                )

    def test_does_not_swallow_into_empty_list(self):
        # 非法入参必须是业务错误，而不是被吞掉后返回空列表
        response = self.client.get("/api/units/", {"page": "abc"})
        self._assert_business_error(response)
        self.assertEqual(Unit.objects.count(), 1)

    def test_valid_pagination_keeps_total_and_ordering(self):
        for i in range(3):
            Unit.objects.create(name=f"单位{i}", created_by=self.user)

        response = self.client.get("/api/units/", {"page": "1", "page_size": "2"})
        self.assertEqual(response.status_code, 200)
        data = response.json()["data"]
        self.assertEqual(data["total"], 4)
        self.assertEqual(data["page"], 1)
        self.assertEqual(data["page_size"], 2)
        self.assertEqual(len(data["list"]), 2)
        # 排序仍为 created_at 倒序：最新创建的在前
        self.assertEqual(data["list"][0]["name"], "单位2")

        page_two = self.client.get("/api/units/", {"page": "2", "page_size": "2"})
        names = [item["name"] for item in page_two.json()["data"]["list"]]
        self.assertEqual(names, ["单位0", "件"])

    def test_page_beyond_range_is_valid_empty_page_with_real_total(self):
        response = self.client.get("/api/units/", {"page": "99"})
        self.assertEqual(response.status_code, 200)
        data = response.json()["data"]
        self.assertEqual(data["list"], [])
        self.assertEqual(data["total"], 1)

    def test_invalid_page_does_not_affect_subsequent_valid_requests(self):
        bad = self.client.get("/api/units/", {"page": "-5"})
        self.assertEqual(bad.status_code, 400)
        good = self.client.get("/api/units/", {"page": "1"})
        self.assertEqual(good.status_code, 200)
        self.assertEqual(good.json()["data"]["total"], 1)
