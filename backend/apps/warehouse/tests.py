from decimal import Decimal
from datetime import timedelta

from django.db import IntegrityError
from django.test import TestCase
from django.utils import timezone
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

    def test_list_units_rejects_invalid_pagination(self):
        for query in ("page=0", "page=-1", "page=abc", "page_size=0", "page_size=-5", "page_size=101"):
            response = self.client.get(f"/api/units/?{query}")
            self.assertEqual(response.status_code, 400, query)
            body = response.json()
            self.assertFalse(body["success"])
            self.assertEqual(body["code"], 400)
            self.assertTrue(body["message"])

    def test_list_categories_rejects_invalid_pagination(self):
        for query in ("page=0", "page=-2", "page=xyz", "page_size=0", "page_size=9999"):
            response = self.client.get(f"/api/categories/?{query}")
            self.assertEqual(response.status_code, 400, query)
            self.assertFalse(response.json()["success"])

    def test_list_units_pagination_keeps_order_and_total(self):
        base = timezone.now()
        # 固定创建时间，保证倒序排列确定
        Unit.objects.filter(pk=self.unit.pk).update(created_at=base - timedelta(hours=3))
        for i, name in enumerate(("箱", "台")):
            unit = Unit.objects.create(name=name, created_by=self.user)
            Unit.objects.filter(pk=unit.pk).update(created_at=base - timedelta(hours=2 - i))

        first = self.client.get("/api/units/?page=1&page_size=2")
        second = self.client.get("/api/units/?page=2&page_size=2")

        self.assertEqual(first.status_code, 200)
        data = first.json()["data"]
        self.assertEqual(data["total"], 3)
        self.assertEqual(data["page"], 1)
        self.assertEqual(data["page_size"], 2)
        self.assertEqual(len(data["list"]), 2)
        # 排序保持创建时间倒序，最新创建的“台”在最前
        self.assertEqual(data["list"][0]["name"], "台")
        self.assertEqual(data["list"][1]["name"], "箱")

        self.assertEqual(second.status_code, 200)
        second_data = second.json()["data"]
        self.assertEqual(second_data["total"], 3)
        self.assertEqual([item["name"] for item in second_data["list"]], ["件"])
