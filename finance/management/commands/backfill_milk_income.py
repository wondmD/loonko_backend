from django.core.management.base import BaseCommand

from farm.models import Farm
from finance.services import backfill_milk_income


class Command(BaseCommand):
    help = 'Rebuild auto milk-income transactions from milk production records.'

    def add_arguments(self, parser):
        parser.add_argument('--days', type=int, default=90)
        parser.add_argument('--farm-id', type=int, default=None)

    def handle(self, *args, **options):
        farm = None
        if options['farm_id']:
            farm = Farm.objects.get(pk=options['farm_id'])
        count = backfill_milk_income(farm=farm, days=options['days'])
        self.stdout.write(
            self.style.SUCCESS(
                f'Upserted {count} daily milk-income transaction(s) '
                f'over the last {options["days"]} day(s).'
            )
        )
