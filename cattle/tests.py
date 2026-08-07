from datetime import timedelta
from decimal import Decimal

from django.utils import timezone
from rest_framework.test import APITestCase
from rest_framework import status

from accounts.models import User
from farm.models import Farm
from cattle.models import Cattle, CattleGrowthLog
from finance.models import Transaction
from alerts.models import Alert
from husbandry.models import HusbandryTask


class CattleEnhancementTests(APITestCase):
    def setUp(self):
        self.farm = Farm.objects.create(name='Test Farm')
        self.owner = User.objects.create_user(
            username='owner',
            email='owner@test.com',
            password='testpass123',
            role=User.Role.OWNER,
            farm=self.farm
        )
        self.client.force_authenticate(user=self.owner)
        
        self.cow = Cattle.objects.create(
            farm=self.farm,
            tag_id='COW-100',
            sex=Cattle.Sex.FEMALE,
            status=Cattle.Status.ACTIVE,
        )

    def test_cattle_sale_financial_linkage(self):
        # Add a pending task
        HusbandryTask.objects.create(
            farm=self.farm,
            cattle=self.cow,
            task_type=HusbandryTask.TaskType.WEANING,
            title='Test Task',
            due_date=timezone.localdate(),
            status=HusbandryTask.Status.PENDING,
            is_auto=True,
        )
        
        # Sell the cow
        res = self.client.patch(f'/api/cattle/{self.cow.id}/', {
            'status': 'SOLD',
            'sale_price': '50000.00',
            'sale_date': timezone.localdate().isoformat(),
        }, format='json')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        
        # Verify task is cancelled
        tasks = HusbandryTask.objects.filter(cattle=self.cow)
        self.assertTrue(all(t.status == HusbandryTask.Status.CANCELLED for t in tasks))
        
        # Verify transaction is created
        txn = Transaction.objects.filter(source_key=f'cattle-sale-{self.cow.id}').first()
        self.assertIsNotNone(txn)
        self.assertEqual(txn.amount, Decimal('50000.00'))
        self.assertEqual(txn.category, Transaction.Category.CATTLE_SALE)
        self.assertEqual(txn.type, Transaction.Type.INCOME)

    def test_cattle_growth_logging_and_alerts(self):
        # Create growth log with low BCS
        res = self.client.post(f'/api/cattle/{self.cow.id}/growth/', {
            'weight_kg': '400.0',
            'bcs': '2.0',
            'date': timezone.localdate().isoformat(),
        }, format='json')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        
        # Verify log is created
        log = CattleGrowthLog.objects.filter(cattle=self.cow).first()
        self.assertIsNotNone(log)
        self.assertEqual(log.bcs, Decimal('2.00'))
        self.assertEqual(log.weight_kg, Decimal('400.00'))
        
        # Verify alert is generated for low BCS
        alert = Alert.objects.filter(cattle=self.cow, category=Alert.Category.HEALTH).first()
        self.assertIsNotNone(alert)
        self.assertIn('Low BCS Alert', alert.title)

    def test_inbreeding_check(self):
        # Setup common sire
        sire = Cattle.objects.create(farm=self.farm, tag_id='BULL-1', sex=Cattle.Sex.MALE)
        dam1 = Cattle.objects.create(farm=self.farm, tag_id='COW-1', sex=Cattle.Sex.FEMALE, father=sire)
        dam2 = Cattle.objects.create(farm=self.farm, tag_id='COW-2', sex=Cattle.Sex.FEMALE, father=sire)
        
        bull2 = Cattle.objects.create(farm=self.farm, tag_id='BULL-2', sex=Cattle.Sex.MALE, mother=dam1)
        
        res = self.client.get(f'/api/cattle/{dam2.id}/inbreeding_check/?sire_id={bull2.id}')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        
        data = res.json()
        self.assertEqual(data['risk_level'], 'MODERATE_WARNING')
        self.assertTrue(data['has_conflict'])
        self.assertEqual(data['common_ancestors'][0]['id'], sire.id)

    def test_age_display_formatting(self):
        today = timezone.localdate()
        
        # 1 year and 2 months
        c1 = Cattle.objects.create(
            farm=self.farm,
            tag_id='AGE-1',
            sex=Cattle.Sex.FEMALE,
            date_of_birth=today.replace(year=today.year - 1, month=(today.month - 2 if today.month > 2 else 12)),
        )
        self.assertIn('year', c1.age_display)
        
        # 8 months
        c2 = Cattle.objects.create(
            farm=self.farm,
            tag_id='AGE-2',
            sex=Cattle.Sex.FEMALE,
            date_of_birth=today - timedelta(days=240),
        )
        self.assertIn('month', c2.age_display)
        
        # 15 days
        c3 = Cattle.objects.create(
            farm=self.farm,
            tag_id='AGE-3',
            sex=Cattle.Sex.FEMALE,
            date_of_birth=today - timedelta(days=15),
        )
        self.assertEqual(c3.age_display, '15 days old')

        # Born today
        c4 = Cattle.objects.create(
            farm=self.farm,
            tag_id='AGE-4',
            sex=Cattle.Sex.FEMALE,
            date_of_birth=today,
        )
        self.assertEqual(c4.age_display, 'Born today')

    def test_cattle_deletion(self):
        # Create a calf linked to cow as mother
        calf = Cattle.objects.create(
            farm=self.farm,
            tag_id='CALF-100',
            sex=Cattle.Sex.FEMALE,
            mother=self.cow,
        )
        
        # Non-owner cannot delete
        worker = User.objects.create_user(
            username='worker', email='worker@test.com', password='password', role=User.Role.WORKER, farm=self.farm
        )
        self.client.force_authenticate(user=worker)
        res = self.client.delete(f'/api/cattle/{self.cow.id}/')
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)
        
        # Owner can delete
        self.client.force_authenticate(user=self.owner)
        res = self.client.delete(f'/api/cattle/{self.cow.id}/')
        self.assertEqual(res.status_code, status.HTTP_204_NO_CONTENT)
        
        # Verify cow is deleted
        self.assertFalse(Cattle.objects.filter(id=self.cow.id).exists())
        
        # Verify calf still exists and mother is set to null
        calf.refresh_from_db()
        self.assertIsNone(calf.mother)
