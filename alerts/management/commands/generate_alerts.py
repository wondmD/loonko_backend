from django.core.management.base import BaseCommand

from alerts.services import generate_due_alerts
from farm.models import Farm


class Command(BaseCommand):
    help = 'Generate vaccination, calving, husbandry, and missed-milk alerts'

    def add_arguments(self, parser):
        parser.add_argument('--farm-id', type=int, default=None)

    def handle(self, *args, **options):
        farm = None
        if options['farm_id']:
            farm = Farm.objects.get(pk=options['farm_id'])
        created = generate_due_alerts(farm=farm)
        self.stdout.write(self.style.SUCCESS(f'Created {created} alert(s).'))
