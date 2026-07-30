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
