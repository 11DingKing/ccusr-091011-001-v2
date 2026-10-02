from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.authentication.backends import generate_token
from apps.authentication.models import User
from .models import StockOutPerson


class StockOutPersonModelTest(TestCase):
    def test_create_and_render_person(self):
        person = StockOutPerson.objects.create(
            police_no="OUT001",
            name="王五",
            phone="13800138000",
        )
        self.assertEqual(person.police_no, "OUT001")
        self.assertIn("王五", str(person))
        self.assertTrue(person.is_active)


class StockOutPersonAPITest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="personnel-user",
            password="testpass123",
            role="admin",
        )
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {generate_token(self.user)}")
        self.url = "/api/stock-out-persons/"

    def test_create_list_update_and_delete_person(self):
        created = self.client.post(
            self.url,
            {
                "police_no": "OUT002",
                "name": "赵六",
                "phone": "13900139000",
                "id_card": "",
            },
            format="json",
        )
        self.assertEqual(created.status_code, 200)
        person_id = created.json()["data"]["id"]

        listed = self.client.get(self.url)
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(listed.json()["data"]["total"], 1)

        updated = self.client.put(
            f"{self.url}{person_id}/",
            {
                "police_no": "OUT002",
                "name": "赵六",
                "phone": "13700137000",
                "id_card": "",
            },
            format="json",
        )
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.json()["data"]["phone"], "13700137000")

        deleted = self.client.delete(f"{self.url}{person_id}/")
        self.assertEqual(deleted.status_code, 200)
        self.assertFalse(StockOutPerson.objects.filter(pk=person_id).exists())

    def test_reject_duplicate_identifiers(self):
        StockOutPerson.objects.create(
            police_no="OUT003",
            name="钱七",
            phone="13600136000",
        )
        response = self.client.post(
            self.url,
            {
                "police_no": "OUT003",
                "name": "孙八",
                "phone": "13500135000",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_list_rejects_invalid_pagination(self):
        for query in ("page=0", "page=-3", "page=abc", "page_size=0", "page_size=-1", "page_size=1000"):
            response = self.client.get(f"{self.url}?{query}")
            self.assertEqual(response.status_code, 400, query)
            body = response.json()
            self.assertFalse(body["success"])
            self.assertEqual(body["code"], 400)

    def test_list_pagination_keeps_order_and_total(self):
        base = timezone.now()
        for i, no in enumerate(("OUT010", "OUT011", "OUT012")):
            person = StockOutPerson.objects.create(
                police_no=no, name=f"警员{no}", phone=f"1380013801{i}"
            )
            # 固定创建时间，保证倒序排列确定
            StockOutPerson.objects.filter(pk=person.pk).update(
                created_at=base - timedelta(hours=3 - i)
            )

        response = self.client.get(f"{self.url}?page=2&page_size=2")

        self.assertEqual(response.status_code, 200)
        data = response.json()["data"]
        self.assertEqual(data["total"], 3)
        self.assertEqual(data["page"], 2)
        self.assertEqual(data["page_size"], 2)
        # 排序保持创建时间倒序，第二页只剩最早创建的一条
        self.assertEqual([item["police_no"] for item in data["list"]], ["OUT010"])
