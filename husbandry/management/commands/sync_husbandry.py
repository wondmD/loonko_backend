from django.core.management.base import BaseCommand

from farm.models import Farm
from husbandry.services import generate_husbandry_alerts, sync_all_female_cattle


class Command(BaseCommand):
    help = 'Sync female cattle husbandry schedules and create due/overdue alerts.'

    def add_arguments(self, parser):
        parser.add_argument('--farm-id', type=int, default=None)
        parser.add_argument(
            '--no-alerts',
            action='store_true',
            help='Only sync tasks; skip alert generation.',
        )

    def handle(self, *args, **options):
        farm = None
        if options['farm_id']:
            farm = Farm.objects.get(pk=options['farm_id'])
        results = sync_all_female_cattle(farm=farm)
        self.stdout.write(
            self.style.SUCCESS(
                f'Synced husbandry for {len(results)} active female cattle.'
            )
        )
        if not options['no_alerts']:
            created = generate_husbandry_alerts(farm=farm)
            self.stdout.write(
                self.style.SUCCESS(f'Created {created} husbandry alert(s).')
            )
