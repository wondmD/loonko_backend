from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone

from breeding.models import BirthRecord, BreedingEvent, Pregnancy
from cattle.models import Cattle
from farm.models import Farm
from finance.models import Transaction
from health.models import HealthRecord, Vaccination
from milk.models import MilkRecord

User = get_user_model()


class Command(BaseCommand):
    help = 'Seed demo farm data (Owner, Workers, Veterinarian, sample records)'

    def handle(self, *args, **options):
        farm, _ = Farm.objects.get_or_create(
            name='Loonkoo Demo Farm',
            defaults={
                'location': 'Adama',
                'region': 'Oromia',
                'woreda': 'Adama',
                'phone': '+251900000000',
                'notes': 'Demo seed data',
                'milk_price_per_liter': Decimal('45.00'),
                'currency': 'ETB',
                'auto_milk_income': True,
                'milk_income_mode': Farm.MilkIncomeMode.ACCRUAL,
            },
        )
        farm.milk_price_per_liter = Decimal('45.00')
        farm.auto_milk_income = True
        farm.currency = 'ETB'
        farm.save()

        users_spec = [
            ('owner@demo.local', 'owner', User.Role.OWNER, 'Demo', 'Owner'),
            ('worker1@demo.local', 'worker1', User.Role.WORKER, 'Abebe', 'Demo'),
            ('worker2@demo.local', 'worker2', User.Role.WORKER, 'Tigist', 'Demo'),
            ('vet@demo.local', 'vet', User.Role.VETERINARIAN, 'Sara', 'Vet'),
        ]
        for email, username, role, first, last in users_spec:
            user, created = User.objects.get_or_create(
                email=email,
                defaults={
                    'username': username,
                    'role': role,
                    'first_name': first,
                    'last_name': last,
                    'farm': farm,
                },
            )
            if created:
                user.set_password('demo1234')
                user.save()
            elif user.farm_id != farm.id:
                user.farm = farm
                user.save(update_fields=['farm'])

        owner = User.objects.get(email='owner@demo.local')
        today = timezone.localdate()

        specs = [
            ('C-001', 'Nala', 45, False),
            ('C-002', 'Bora', 70, False),
            ('C-003', 'Aster', 300, False),
            ('C-004', 'Lomi', 500, False),
            ('C-005', 'Saron', 600, False),
            ('C-006', 'Marta', 365 * 4, True),
            ('C-007', 'Hana', 365 * 5, True),
            ('C-008', 'Tigist', 365 * 3, True),
            ('C-009', 'Selam', 365 * 6, True),
            ('C-010', 'Abeba', 365 * 4, True),
        ]

        cows = []
        for tag, name, age_days, _is_cow in specs:
            cow, _ = Cattle.objects.get_or_create(
                farm=farm,
                tag_id=tag,
                defaults={
                    'name': name,
                    'breed': 'Holstein' if age_days % 2 else 'Boran',
                    'sex': Cattle.Sex.FEMALE,
                    'date_of_birth': today - timedelta(days=age_days),
                    'status': Cattle.Status.ACTIVE,
                },
            )
            cow.date_of_birth = today - timedelta(days=age_days)
            cow.name = name
            if cow.photo_front:
                cow.photo_front.delete(save=False)
            if cow.photo_left:
                cow.photo_left.delete(save=False)
            if cow.photo_right:
                cow.photo_right.delete(save=False)
            cow.photo_front = None
            cow.photo_left = None
            cow.photo_right = None
            cow.farm = farm
            cow.save()
            cows.append(cow)

        for day_offset in range(30):
            day = today - timedelta(days=day_offset)
            for cow in cows[5:]:
                MilkRecord.objects.get_or_create(
                    farm=farm,
                    cattle=cow,
                    date=day,
                    defaults={
                        'morning_liters': Decimal('6.5'),
                        'evening_liters': Decimal('5.5'),
                        'recorded_by': owner,
                    },
                )

        Vaccination.objects.get_or_create(
            farm=farm,
            cattle=cows[5],
            vaccine_name='FMD',
            administered_on=today - timedelta(days=180),
            defaults={
                'next_due_on': today + timedelta(days=3),
                'veterinarian_name': 'Dr. Sara',
                'recorded_by': owner,
            },
        )

        HealthRecord.objects.get_or_create(
            farm=farm,
            cattle=cows[6],
            recorded_at=timezone.now() - timedelta(days=2),
            defaults={
                'symptoms': ['cough', 'reduced appetite'],
                'severity': HealthRecord.Severity.MEDIUM,
                'notes': 'Monitor for 48h',
                'recorded_by': owner,
            },
        )

        fresh = cows[5]
        preg_fresh, _ = Pregnancy.objects.get_or_create(
            farm=farm,
            cattle=fresh,
            defaults={
                'status': Pregnancy.Status.CALVED,
                'confirmed_on': today - timedelta(days=300),
                'expected_calving_date': today - timedelta(days=10),
            },
        )
        BirthRecord.objects.get_or_create(
            farm=farm,
            pregnancy=preg_fresh,
            defaults={
                'calving_date': today - timedelta(days=10),
                'calf_tag_id': 'C-011',
                'calf_sex': Cattle.Sex.FEMALE,
                'notes': 'Demo fresh calving',
            },
        )

        near = cows[6]
        event, _ = BreedingEvent.objects.get_or_create(
            farm=farm,
            dam=near,
            mating_date=today - timedelta(days=270),
            defaults={'method': BreedingEvent.Method.AI, 'notes': 'Demo breeding'},
        )
        Pregnancy.objects.update_or_create(
            farm=farm,
            cattle=near,
            breeding_event=event,
            defaults={
                'status': Pregnancy.Status.PREGNANT,
                'confirmed_on': today - timedelta(days=230),
                'expected_calving_date': today + timedelta(days=10),
            },
        )

        dry_cow = cows[7]
        event2, _ = BreedingEvent.objects.get_or_create(
            farm=farm,
            dam=dry_cow,
            mating_date=today - timedelta(days=240),
            defaults={'method': BreedingEvent.Method.AI, 'notes': 'Dry-period demo'},
        )
        Pregnancy.objects.update_or_create(
            farm=farm,
            cattle=dry_cow,
            breeding_event=event2,
            defaults={
                'status': Pregnancy.Status.PREGNANT,
                'confirmed_on': today - timedelta(days=200),
                'expected_calving_date': today + timedelta(days=45),
            },
        )

        open_cow = cows[8]
        preg_old, _ = Pregnancy.objects.get_or_create(
            farm=farm,
            cattle=open_cow,
            defaults={
                'status': Pregnancy.Status.CALVED,
                'confirmed_on': today - timedelta(days=400),
                'expected_calving_date': today - timedelta(days=120),
            },
        )
        BirthRecord.objects.get_or_create(
            farm=farm,
            pregnancy=preg_old,
            defaults={
                'calving_date': today - timedelta(days=120),
                'notes': 'Older calving — open past VWP',
            },
        )

        cow9 = cows[9]
        preg9, _ = Pregnancy.objects.get_or_create(
            farm=farm,
            cattle=cow9,
            defaults={
                'status': Pregnancy.Status.CALVED,
                'confirmed_on': today - timedelta(days=500),
                'expected_calving_date': today - timedelta(days=200),
            },
        )
        BirthRecord.objects.get_or_create(
            farm=farm,
            pregnancy=preg9,
            defaults={
                'calving_date': today - timedelta(days=200),
                'notes': 'Lactating cow demo',
            },
        )

        Transaction.objects.get_or_create(
            farm=farm,
            type=Transaction.Type.INCOME,
            category=Transaction.Category.MILK_SALE,
            date=today,
            amount=Decimal('5000.00'),
            defaults={
                'description': 'Cash received from milk buyer (manual)',
                'recorded_by': owner,
                'is_auto': False,
            },
        )
        Transaction.objects.get_or_create(
            farm=farm,
            type=Transaction.Type.EXPENSE,
            category=Transaction.Category.FEED,
            date=today - timedelta(days=1),
            amount=Decimal('1200.00'),
            defaults={'description': 'Feed purchase', 'recorded_by': owner},
        )

        from finance.services import backfill_milk_income
        from husbandry.services import sync_all_female_cattle

        milk_txns = backfill_milk_income(farm=farm, days=30)
        sync_all_female_cattle(farm=farm)

        self.stdout.write(self.style.SUCCESS(f'Demo data ready for farm: {farm.name} (id={farm.id})'))
        self.stdout.write(f'  Auto milk income days booked: {milk_txns}')
        self.stdout.write('  owner@demo.local / demo1234')
        self.stdout.write('  worker1@demo.local / demo1234')
        self.stdout.write('  worker2@demo.local / demo1234')
        self.stdout.write('  vet@demo.local / demo1234')
