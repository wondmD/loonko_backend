from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from cattle.models import Cattle
from farm.models import Farm

User = get_user_model()


class AuthAndPermissionsTests(APITestCase):
    def setUp(self):
        self.farm = Farm.objects.create(name='Test Farm', region='Oromia')
        self.owner = User.objects.create_user(
            username='owner',
            email='owner@test.local',
            password='testpass123',
            role=User.Role.OWNER,
            farm=self.farm,
        )
        self.worker = User.objects.create_user(
            username='worker',
            email='worker@test.local',
            password='testpass123',
            role=User.Role.WORKER,
            farm=self.farm,
        )
        self.vet = User.objects.create_user(
            username='vet',
            email='vet@test.local',
            password='testpass123',
            role=User.Role.VETERINARIAN,
            farm=self.farm,
        )
        self.cow = Cattle.objects.create(farm=self.farm, tag_id='T-001', name='Bessie', breed='Holstein')

    def _login(self, email):
        res = self.client.post(
            '/api/auth/login/',
            {'email': email, 'password': 'testpass123'},
            format='json',
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK, res.content)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {res.data['access']}")

    def test_me_requires_auth(self):
        res = self.client.get('/api/auth/me/')
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_owner_can_access_finance(self):
        self._login('owner@test.local')
        res = self.client.get('/api/finance/summary/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)

    def test_worker_cannot_access_finance(self):
        self._login('worker@test.local')
        res = self.client.get('/api/finance/summary/')
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_vet_cannot_write_milk(self):
        self._login('vet@test.local')
        res = self.client.post(
            '/api/milk/records/',
            {
                'cattle': self.cow.id,
                'date': '2026-07-01',
                'morning_liters': '5.0',
                'evening_liters': '4.0',
            },
            format='json',
        )
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_vet_can_write_health(self):
        self._login('vet@test.local')
        res = self.client.post(
            '/api/health/records/',
            {
                'cattle': self.cow.id,
                'recorded_at': '2026-07-01T10:00:00Z',
                'symptoms': ['fever'],
                'severity': 'MEDIUM',
            },
            format='json',
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)

    def test_worker_cannot_invite_staff(self):
        self._login('worker@test.local')
        res = self.client.post(
            '/api/auth/staff/',
            {
                'email': 'new@test.local',
                'password': 'testpass123',
                'role': 'WORKER',
            },
            format='json',
        )
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_farm_singleton(self):
        self._login('owner@test.local')
        res = self.client.post('/api/farm/', {'name': 'Another'}, format='json')
        self.assertEqual(res.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_unique_milk_per_day(self):
        self._login('owner@test.local')
        payload = {
            'cattle': self.cow.id,
            'date': '2026-07-02',
            'morning_liters': '5.0',
            'evening_liters': '4.0',
        }
        r1 = self.client.post('/api/milk/records/', payload, format='json')
        self.assertEqual(r1.status_code, status.HTTP_201_CREATED)
        r2 = self.client.post('/api/milk/records/', payload, format='json')
        self.assertEqual(r2.status_code, status.HTTP_400_BAD_REQUEST)
