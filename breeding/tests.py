from datetime import timedelta
from django.utils import timezone
from rest_framework.test import APITestCase
from rest_framework import status

from accounts.models import User
from farm.models import Farm
from cattle.models import Cattle
from breeding.models import Pregnancy, BirthRecord, BreedingEvent
from husbandry.planning import classify_animal


class HusbandryClassificationAndCalvingValidationTests(APITestCase):
    def setUp(self):
        self.farm = Farm.objects.create(name="Alpha Dairy Farm")
        self.owner = User.objects.create_user(
            username="farm_owner",
            password="testpassword123",
            role=User.Role.OWNER,
            farm=self.farm,
        )
        self.client.force_authenticate(user=self.owner)

    def test_mature_cow_classification_without_calving_history(self):
        """Ensure an 8-year-old or 2+ year old female cattle is categorized as COW, not HEIFER."""
        today = timezone.localdate()
        # 8-year-old cow (2920 days) with 0 calvings
        old_cow = Cattle.objects.create(
            farm=self.farm,
            tag_id="OLD-COW-01",
            sex=Cattle.Sex.FEMALE,
            date_of_birth=today - timedelta(days=365 * 8),
            status=Cattle.Status.ACTIVE,
        )
        classification = classify_animal(old_cow)
        self.assertEqual(classification["category"], "COW")
        self.assertEqual(classification["code"], "OPEN_COW")

        # Young heifer (300 days old)
        heifer = Cattle.objects.create(
            farm=self.farm,
            tag_id="HEIFER-01",
            sex=Cattle.Sex.FEMALE,
            date_of_birth=today - timedelta(days=300),
            status=Cattle.Status.ACTIVE,
        )
        heifer_classification = classify_animal(heifer)
        self.assertEqual(heifer_classification["category"], "HEIFER")

        # Calf (60 days old)
        calf = Cattle.objects.create(
            farm=self.farm,
            tag_id="CALF-01",
            sex=Cattle.Sex.FEMALE,
            date_of_birth=today - timedelta(days=60),
            status=Cattle.Status.ACTIVE,
        )
        calf_classification = classify_animal(calf)
        self.assertEqual(calf_classification["category"], "CALF")

    def test_calving_validation_prevents_calf_birth_record(self):
        """Ensure birth records cannot be registered for a calf dam."""
        today = timezone.localdate()
        calf_dam = Cattle.objects.create(
            farm=self.farm,
            tag_id="CALF-DAM",
            sex=Cattle.Sex.FEMALE,
            date_of_birth=today - timedelta(days=60),
        )
        preg = Pregnancy.objects.create(
            farm=self.farm,
            cattle=calf_dam,
            status=Pregnancy.Status.PREGNANT,
            confirmed_on=today - timedelta(days=30),
            expected_calving_date=today,
        )

        res = self.client.post("/api/breeding/births/", {
            "pregnancy": preg.id,
            "calving_date": today.isoformat(),
        }, format="json")

        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("calf", str(res.data).lower())

    def test_calving_validation_enforces_270_day_interval(self):
        """Ensure consecutive calvings for the same dam require at least 270 days (9 months)."""
        today = timezone.localdate()
        dam = Cattle.objects.create(
            farm=self.farm,
            tag_id="DAM-101",
            sex=Cattle.Sex.FEMALE,
            date_of_birth=today - timedelta(days=1500),
        )
        # First calving 100 days ago
        preg1 = Pregnancy.objects.create(
            farm=self.farm,
            cattle=dam,
            status=Pregnancy.Status.CALVED,
            confirmed_on=today - timedelta(days=380),
            expected_calving_date=today - timedelta(days=100),
        )
        BirthRecord.objects.create(
            farm=self.farm,
            pregnancy=preg1,
            calving_date=today - timedelta(days=100),
        )

        # Second pregnancy attempting calving today (only 100 days later < 270 days)
        preg2 = Pregnancy.objects.create(
            farm=self.farm,
            cattle=dam,
            status=Pregnancy.Status.PREGNANT,
            confirmed_on=today - timedelta(days=30),
            expected_calving_date=today,
        )

        res = self.client.post("/api/breeding/births/", {
            "pregnancy": preg2.id,
            "calving_date": today.isoformat(),
        }, format="json")

        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("270 days", str(res.data))

        # Calving at 300 days later should succeed
        valid_calving_date = today - timedelta(days=100) + timedelta(days=300)
        # Assuming valid_calving_date <= today:
        if valid_calving_date <= today:
            res_valid = self.client.post("/api/breeding/births/", {
                "pregnancy": preg2.id,
                "calving_date": valid_calving_date.isoformat(),
            }, format="json")
            self.assertEqual(res_valid.status_code, status.HTTP_201_CREATED)

    def test_calving_future_date_rejected(self):
        """Ensure calving dates in the future are rejected."""
        today = timezone.localdate()
        dam = Cattle.objects.create(
            farm=self.farm,
            tag_id="DAM-102",
            sex=Cattle.Sex.FEMALE,
            date_of_birth=today - timedelta(days=1500),
        )
        preg = Pregnancy.objects.create(
            farm=self.farm,
            cattle=dam,
            status=Pregnancy.Status.PREGNANT,
            confirmed_on=today - timedelta(days=50),
            expected_calving_date=today + timedelta(days=10),
        )

        res = self.client.post("/api/breeding/births/", {
            "pregnancy": preg.id,
            "calving_date": (today + timedelta(days=5)).isoformat(),
        }, format="json")

        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("future", str(res.data).lower())

    def test_reproductive_intake_single_last_calving_for_mature_cow(self):
        """Verify onboarding a non-pregnant mature cow creates a single authentic BirthRecord."""
        today = timezone.localdate()
        dob = (today - timedelta(days=1200)).isoformat()
        last_calving = (today - timedelta(days=150)).isoformat()

        import io
        from PIL import Image

        def make_dummy_img():
            file = io.BytesIO()
            img = Image.new("RGB", (100, 100), color="white")
            img.save(file, "jpeg")
            file.name = "test.jpg"
            file.seek(0)
            return file

        res = self.client.post(
            "/api/cattle/",
            {
                "tag_id": "ONBOARD-COW-1",
                "name": "Daisy",
                "breed": "Jersey",
                "sex": "FEMALE",
                "date_of_birth": dob,
                "is_pregnant": "false",
                "last_calving_date": last_calving,
                "photo_front": make_dummy_img(),
                "photo_left": make_dummy_img(),
                "photo_right": make_dummy_img(),
            },
            format="multipart",
        )

        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        cattle_id = res.data["id"]
        cattle = Cattle.objects.get(id=cattle_id)

        # Verify only 1 BirthRecord was created
        births = BirthRecord.objects.filter(pregnancy__cattle=cattle)
        self.assertEqual(births.count(), 1)
        self.assertEqual(births.first().calving_date.isoformat(), last_calving)
