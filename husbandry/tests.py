from datetime import timedelta
from django.utils import timezone
from rest_framework.test import APITestCase

from accounts.models import User
from alerts.models import Alert
from breeding.models import BreedingEvent, Pregnancy, BirthRecord
from cattle.models import Cattle
from farm.models import Farm
from finance.models import Transaction
from health.models import HealthRecord, Vaccination, Treatment
from husbandry.models import HusbandryTask
from milk.models import MilkRecord, FeedSchedule


class CrossModuleSyncIntegrationTests(APITestCase):
    def setUp(self):
        self.farm = Farm.objects.create(
            name="Loonkoo Dairy Farm",
            region="Oromia",
            milk_price_per_liter="50.00",
            auto_milk_income=True,
        )
        self.owner = User.objects.create_user(
            username="owner_sync",
            email="owner_sync@test.local",
            password="testpass123",
            role=User.Role.OWNER,
            farm=self.farm,
        )
        self.client.force_authenticate(user=self.owner)

        # Create a breeding cow
        self.cow = Cattle.objects.create(
            farm=self.farm,
            tag_id="COW-100",
            name="Bella",
            breed="Holstein",
            sex=Cattle.Sex.FEMALE,
            date_of_birth=timezone.localdate() - timedelta(days=1000),
        )

    def test_end_to_end_dairy_farm_lifecycle_sync(self):
        # 1. Verify cattle creation synced initial husbandry tasks
        self.assertTrue(self.cow.husbandry_tasks.exists())

        # 2. Record Artificial Insemination (BreedingEvent)
        mating_date = timezone.localdate() - timedelta(days=280)
        breeding_event = BreedingEvent.objects.create(
            farm=self.farm,
            dam=self.cow,
            mating_date=mating_date,
            notes="Semen code: HOL-999",
        )
        self.assertIsNotNone(breeding_event.pk)

        # 3. Record Pregnancy Confirmation
        pregnancy = Pregnancy.objects.create(
            farm=self.farm,
            cattle=self.cow,
            breeding_event=breeding_event,
            confirmed_on=mating_date + timedelta(days=35),
            expected_calving_date=mating_date + timedelta(days=280),
            status=Pregnancy.Status.PREGNANT,
        )
        self.assertIsNotNone(pregnancy.pk)

        # 4. Record Birth (BirthRecord) -> Auto-creates Calf & Auto-completes Calving tasks
        calving_date = timezone.localdate() - timedelta(days=10)
        birth = BirthRecord.objects.create(
            farm=self.farm,
            pregnancy=pregnancy,
            calving_date=calving_date,
            calf_tag_id="CALF-200",
            calf_sex=Cattle.Sex.FEMALE,
            notes="Luna, 35.0kg",
        )
        self.assertIsNotNone(birth.calf)
        self.assertEqual(birth.calf.tag_id, "CALF-200")
        self.assertEqual(birth.calf.mother_id, self.cow.id)

        # 5. Record Milk Production -> Auto-syncs Milk Sale Income in Finance
        today = timezone.localdate()
        milk_record = MilkRecord.objects.create(
            farm=self.farm,
            cattle=self.cow,
            date=today,
            morning_liters="15.50",
            evening_liters="14.50",
            recorded_by=self.owner,
        )
        income_tx = Transaction.objects.filter(
            farm=self.farm,
            type=Transaction.Type.INCOME,
            category=Transaction.Category.MILK_PRODUCTION,
            date=today,
        ).first()
        self.assertIsNotNone(income_tx)
        # 30 liters * 50 ETB = 1500 ETB
        self.assertEqual(income_tx.amount, 1500.0)

        # 6. Record Vaccination with Cost -> Auto-syncs Vaccination Expense in Finance
        vaccination = Vaccination.objects.create(
            farm=self.farm,
            cattle=self.cow,
            vaccine_name="Foot and Mouth Disease",
            administered_on=today,
            cost="250.00",
            next_due_on=today + timedelta(days=180),
            recorded_by=self.owner,
        )
        vac_expense = Transaction.objects.filter(
            farm=self.farm,
            type=Transaction.Type.EXPENSE,
            category=Transaction.Category.VET,
            description__icontains="Vaccination: Foot and Mouth Disease",
        ).first()
        self.assertIsNotNone(vac_expense)
        self.assertEqual(vac_expense.amount, 250.0)

        # 7. Record Health Treatment with Cost -> Auto-syncs Treatment Expense & Alert
        treatment = Treatment.objects.create(
            farm=self.farm,
            cattle=self.cow,
            diagnosis="Mastitis Mild",
            medication="Penicillin",
            start_date=today,
            cost="400.00",
            recorded_by=self.owner,
        )
        treatment_expense = Transaction.objects.filter(
            farm=self.farm,
            type=Transaction.Type.EXPENSE,
            category=Transaction.Category.VET,
            description__icontains="Treatment: Mastitis Mild",
        ).first()
        self.assertIsNotNone(treatment_expense)
        self.assertEqual(treatment_expense.amount, 400.0)

        treatment_alert = Alert.objects.filter(
            farm=self.farm,
            cattle=self.cow,
            category=Alert.Category.HEALTH,
            title__icontains="Treatment started",
        ).first()
        self.assertIsNotNone(treatment_alert)

        # 8. Record Feed Schedule with Cost -> Auto-syncs Feed Expense in Finance
        feed = FeedSchedule.objects.create(
            farm=self.farm,
            cattle=self.cow,
            feed_type="Alfalfa & Concentrate",
            quantity="20.00",
            cost="300.00",
            date=today,
        )
        feed_expense = Transaction.objects.filter(
            farm=self.farm,
            type=Transaction.Type.EXPENSE,
            category=Transaction.Category.FEED,
            date=today,
        ).first()
        self.assertIsNotNone(feed_expense)
        self.assertEqual(feed_expense.amount, 300.0)
