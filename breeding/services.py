"""Breeding herd overview, upcoming board, and per-cow cycle history."""

from datetime import timedelta

from django.utils import timezone

from .models import BirthRecord, BreedingEvent, Pregnancy
from .serializers import (
    BirthRecordSerializer,
    BreedingEventSerializer,
    PregnancySerializer,
)

BREEDING_TASK_TYPES = (
    'FIRST_BREEDING',
    'HEAT_WATCH',
    'BREEDING',
    'PREGNANCY_CHECK',
    'DRY_OFF',
    'CALVING_PREP',
    'CALVING',
    'REBREEDING',
)

# Prefer these labels in the "upcoming event" column
EVENT_TITLE_HINTS = {
    'PREGNANCY_CHECK': 'Confirm pregnancy',
    'BREEDING': 'Next insemination',
    'HEAT_WATCH': 'Heat detection',
    'FIRST_BREEDING': 'First breeding',
    'REBREEDING': 'Rebreeding eligible',
    'CALVING': 'Expected calving',
    'CALVING_PREP': 'Calving preparation',
    'DRY_OFF': 'Dry-off',
}


def pregnancy_state_for(cattle):
    """
    Map open/confirmed pregnancy to UI states:
    pregnant | unconfirmed | not_pregnant
    """
    confirmed = cattle.active_pregnancy()
    if confirmed:
        return {
            'pregnancy_state': 'pregnant',
            'pregnancy_state_label': 'Pregnant',
            'pregnancy': confirmed,
            'open_pregnancy': None,
        }

    open_preg = (
        cattle.pregnancies.filter(status=Pregnancy.Status.OPEN)
        .order_by('-created_at')
        .first()
    )
    if open_preg:
        return {
            'pregnancy_state': 'unconfirmed',
            'pregnancy_state_label': 'Unconfirmed',
            'pregnancy': None,
            'open_pregnancy': open_preg,
        }

    return {
        'pregnancy_state': 'not_pregnant',
        'pregnancy_state_label': 'Not pregnant',
        'pregnancy': None,
        'open_pregnancy': None,
    }


def _iso(d):
    return d.isoformat() if d else None


def _next_breeding_focus(cattle, state, today=None):
    """
    Best next breeding action for the table column.
    Prefers pending husbandry tasks, then derived pregnancy/AI milestones.
    """
    today = today or timezone.localdate()
    from husbandry.models import HusbandryTask

    task = (
        cattle.husbandry_tasks.filter(
            status=HusbandryTask.Status.PENDING,
            task_type__in=BREEDING_TASK_TYPES,
            due_date__gte=cattle.registered_on,
        )
        .order_by('due_date', 'priority')
        .first()
    )
    if task:
        return {
            'type': task.task_type,
            'title': EVENT_TITLE_HINTS.get(task.task_type, task.title),
            'detail': task.title,
            'date': task.due_date.isoformat(),
            'days_until': (task.due_date - today).days,
            'is_overdue': task.due_date < today,
            'priority': task.priority,
            'task_id': task.id,
        }

    preg = state['pregnancy'] or state['open_pregnancy']
    if state['pregnancy_state'] == 'pregnant' and preg and preg.expected_calving_date:
        ecd = preg.expected_calving_date
        dry = ecd - timedelta(days=cattle.DRY_PERIOD_DAYS)
        if dry >= today:
            return {
                'type': 'DRY_OFF',
                'title': EVENT_TITLE_HINTS['DRY_OFF'],
                'detail': 'Estimated dry-off before calving',
                'date': dry.isoformat(),
                'days_until': (dry - today).days,
                'is_overdue': False,
                'priority': 'HIGH',
                'task_id': None,
            }
        return {
            'type': 'CALVING',
            'title': EVENT_TITLE_HINTS['CALVING'],
            'detail': 'Expected calving date',
            'date': ecd.isoformat(),
            'days_until': (ecd - today).days,
            'is_overdue': ecd < today,
            'priority': 'CRITICAL',
            'task_id': None,
        }

    if state['pregnancy_state'] == 'unconfirmed' and preg:
        last = cattle.last_breeding_event()
        check_on = None
        if last:
            from husbandry.planning import get_settings

            settings = get_settings(cattle.farm)
            check_on = last.mating_date + timedelta(days=settings.pregnancy_check_days)
        elif preg.expected_calving_date:
            # Rough fallback: ECD - (gestation - check days) is messy; use created+45
            check_on = today
        if check_on:
            return {
                'type': 'PREGNANCY_CHECK',
                'title': EVENT_TITLE_HINTS['PREGNANCY_CHECK'],
                'detail': 'Diagnose pregnancy after AI/service',
                'date': check_on.isoformat(),
                'days_until': (check_on - today).days,
                'is_overdue': check_on < today,
                'priority': 'HIGH',
                'task_id': None,
            }

    # Open cow / heifer — next breed opportunity
    last_calving = cattle.last_calving_date()
    from husbandry.planning import get_settings

    settings = get_settings(cattle.farm)
    if last_calving:
        vwp_end = last_calving + timedelta(days=settings.voluntary_waiting_days)
        due = max(vwp_end, today)
        return {
            'type': 'BREEDING',
            'title': EVENT_TITLE_HINTS['BREEDING'],
            'detail': 'Breed on confirmed heat after VWP',
            'date': due.isoformat(),
            'days_until': (due - today).days,
            'is_overdue': due < today,
            'priority': 'HIGH',
            'task_id': None,
        }

    if cattle.date_of_birth:
        first = cattle.date_of_birth + timedelta(days=settings.first_breeding_age_days)
        due = max(first, today)
        return {
            'type': 'FIRST_BREEDING',
            'title': EVENT_TITLE_HINTS['FIRST_BREEDING'],
            'detail': 'Heifer first breeding window',
            'date': due.isoformat(),
            'days_until': (due - today).days,
            'is_overdue': first < today,
            'priority': 'NORMAL',
            'task_id': None,
        }

    return None


def _action_hint(state, next_event):
    if state['pregnancy_state'] == 'unconfirmed':
        return 'Confirm or clear pregnancy'
    if state['pregnancy_state'] == 'pregnant':
        if next_event and next_event['type'] in ('CALVING', 'CALVING_PREP'):
            return 'Prepare for calving'
        if next_event and next_event['type'] == 'DRY_OFF':
            return 'Schedule dry-off'
        return 'Monitor pregnancy'
    if next_event and next_event['type'] in ('BREEDING', 'HEAT_WATCH', 'REBREEDING', 'FIRST_BREEDING'):
        return 'Watch heat / inseminate'
    return 'Review breeding status'


def _herd_row(cattle, today):
    state = pregnancy_state_for(cattle)
    last_breeding = cattle.last_breeding_event()
    last_calving = cattle.last_calving_date()
    preg = state['pregnancy'] or state['open_pregnancy']
    next_event = _next_breeding_focus(cattle, state, today=today)

    ecd = preg.expected_calving_date if preg else None
    days_open = None
    if state['pregnancy_state'] == 'not_pregnant' and last_calving:
        days_open = (today - last_calving).days

    days_since_ai = None
    if last_breeding:
        days_since_ai = (today - last_breeding.mating_date).days

    lactation = cattle.lactation_info()

    return {
        'cattle_id': cattle.id,
        'cattle_number': cattle.tag_id,
        'name': cattle.name or '',
        'pregnancy_state': state['pregnancy_state'],
        'pregnancy_state_label': state['pregnancy_state_label'],
        'pregnancy_id': preg.id if preg else None,
        'pregnancy_status_raw': preg.status if preg else None,
        'last_insemination_date': _iso(last_breeding.mating_date) if last_breeding else None,
        'breeding_method': last_breeding.method if last_breeding else None,
        'days_since_insemination': days_since_ai,
        'expected_calving_date': _iso(ecd),
        'days_to_calving': (ecd - today).days if ecd else None,
        'last_calving_date': _iso(last_calving),
        'days_open': days_open,
        'lactation_stage': lactation.get('stage'),
        'lactation_stage_label': lactation.get('stage_label'),
        'next_event': next_event,
        'action_hint': _action_hint(state, next_event),
        'can_confirm_pregnancy': state['pregnancy_state'] == 'unconfirmed',
        'can_record_calving': state['pregnancy_state'] == 'pregnant',
    }


def herd_breeding_overview(farm):
    """Active females relevant to breeding management."""
    from cattle.models import Cattle

    today = timezone.localdate()
    cows = list(
        Cattle.objects.filter(
            farm=farm,
            sex=Cattle.Sex.FEMALE,
            status=Cattle.Status.ACTIVE,
        ).order_by('tag_id')
    )

    dam_ids = set(
        BreedingEvent.objects.filter(farm=farm).values_list('dam_id', flat=True)
    )
    preg_ids = set(
        Pregnancy.objects.filter(farm=farm).values_list('cattle_id', flat=True)
    )
    birth_ids = set(
        BirthRecord.objects.filter(farm=farm).values_list(
            'pregnancy__cattle_id', flat=True
        )
    )
    known = dam_ids | preg_ids | birth_ids

    rows = []
    for cow in cows:
        # Include known breeders + breeding-age / post-calving females
        age = cow.age_days
        include = (
            cow.id in known
            or cow.last_calving_date() is not None
            or (age is not None and age >= 300)
        )
        if not include:
            continue
        rows.append(_herd_row(cow, today))

    # Sort: overdue next, then by days_until, then tag
    def sort_key(row):
        ev = row.get('next_event')
        if not ev:
            return (2, 9999, row['cattle_number'])
        overdue = 0 if ev.get('is_overdue') else 1
        return (overdue, ev.get('days_until', 9999), row['cattle_number'])

    rows.sort(key=sort_key)
    return {'count': len(rows), 'results': rows}


def breeding_upcoming_board(farm, days=30):
    """Breeding-focused task board (overdue / today / upcoming)."""
    from husbandry.models import HusbandryTask
    from husbandry.serializers import HusbandryTaskSerializer

    today = timezone.localdate()
    window_end = today + timedelta(days=days)

    qs = (
        HusbandryTask.objects.filter(
            farm=farm,
            status=HusbandryTask.Status.PENDING,
            task_type__in=BREEDING_TASK_TYPES,
            cattle__sex='FEMALE',
            cattle__status='ACTIVE',
            due_date__lte=window_end,
        )
        .select_related('cattle')
        .order_by('due_date', 'priority')
    )

    # Drop pre-registration leftovers
    filtered = [t for t in qs if t.due_date >= t.cattle.registered_on]

    def enrich(task):
        state = pregnancy_state_for(task.cattle)
        data = HusbandryTaskSerializer(task).data
        data['cattle_number'] = task.cattle.tag_id
        data['cattle_name'] = task.cattle.name or ''
        data['pregnancy_state'] = state['pregnancy_state']
        data['pregnancy_state_label'] = state['pregnancy_state_label']
        data['event_title'] = EVENT_TITLE_HINTS.get(task.task_type, task.title)
        return data

    overdue = [enrich(t) for t in filtered if t.due_date < today]
    due_today = [enrich(t) for t in filtered if t.due_date == today]
    upcoming = [enrich(t) for t in filtered if t.due_date > today]

    # Also surface derived focuses for cows with no pending breeding task yet
    from datetime import date as date_cls

    herd = herd_breeding_overview(farm)['results']
    covered = {t.cattle_id for t in filtered}
    for row in herd:
        if row['cattle_id'] in covered:
            continue
        ev = row.get('next_event')
        if not ev or not ev.get('date'):
            continue
        due = date_cls.fromisoformat(str(ev['date'])[:10])
        if due > window_end:
            continue
        item = {
            'id': None,
            'cattle': row['cattle_id'],
            'cattle_number': row['cattle_number'],
            'cattle_name': row['name'],
            'cattle_tag': row['cattle_number'],
            'task_type': ev['type'],
            'title': ev['title'],
            'event_title': ev['title'],
            'description': ev.get('detail') or '',
            'due_date': ev['date'],
            'days_until': ev['days_until'],
            'is_overdue': ev['is_overdue'],
            'priority': ev.get('priority') or 'NORMAL',
            'status': 'PENDING',
            'pregnancy_state': row['pregnancy_state'],
            'pregnancy_state_label': row['pregnancy_state_label'],
            'is_derived': True,
        }
        if due < today:
            overdue.append(item)
        elif due == today:
            due_today.append(item)
        else:
            upcoming.append(item)

    def by_due(items):
        return sorted(items, key=lambda x: (x.get('due_date') or '', x.get('cattle_number') or ''))

    return {
        'overdue': by_due(overdue),
        'due_today': by_due(due_today),
        'upcoming': by_due(upcoming),
        'counts': {
            'overdue': len(overdue),
            'due_today': len(due_today),
            'upcoming': len(upcoming),
        },
        'days': days,
    }


def cattle_breeding_history(cattle):
    """Breeding cycles newest-first for one cow."""
    today = timezone.localdate()
    state = pregnancy_state_for(cattle)
    summary = _herd_row(cattle, today)

    events = list(
        BreedingEvent.objects.filter(dam=cattle).order_by('-mating_date')
    )
    pregnancies = list(
        Pregnancy.objects.filter(cattle=cattle).order_by('-created_at')
    )
    births = list(
        BirthRecord.objects.filter(pregnancy__cattle=cattle)
        .select_related('pregnancy', 'calf')
        .order_by('-calving_date')
    )

    # Build cycles from births (completed) + current open/pregnant + unmatched matings
    cycles = []

    # Current open/confirmed pregnancy as top cycle if no birth yet for it
    current_preg = state['pregnancy'] or state['open_pregnancy']
    if current_preg:
        mating = current_preg.breeding_event
        if mating is None and events:
            # best effort: last mating on/before pregnancy create
            mating = events[0]
        outcome = (
            'pregnant'
            if current_preg.status == Pregnancy.Status.PREGNANT
            else 'unconfirmed'
            if current_preg.status == Pregnancy.Status.OPEN
            else current_preg.status.lower()
        )
        cycles.append(
            {
                'cycle_index': None,
                'is_current': True,
                'label': (
                    'Current pregnancy'
                    if outcome == 'pregnant'
                    else 'Awaiting pregnancy confirmation'
                ),
                'outcome': outcome,
                'mating': BreedingEventSerializer(mating).data if mating else None,
                'pregnancy': PregnancySerializer(current_preg).data,
                'birth': None,
                'expected_calving_date': _iso(current_preg.expected_calving_date),
                'calving_date': None,
            }
        )

    for index, birth in enumerate(births):
        preg = birth.pregnancy
        mating = preg.breeding_event if preg else None
        cycles.append(
            {
                'cycle_index': len(births) - index,
                'is_current': False,
                'label': f'Calving {len(births) - index} · {birth.calving_date.isoformat()}',
                'outcome': 'calved',
                'mating': BreedingEventSerializer(mating).data if mating else None,
                'pregnancy': PregnancySerializer(preg).data if preg else None,
                'birth': BirthRecordSerializer(birth).data,
                'expected_calving_date': _iso(
                    preg.expected_calving_date if preg else None
                ),
                'calving_date': birth.calving_date.isoformat(),
            }
        )

    # Failed pregnancies without birth
    for preg in pregnancies:
        if preg.status != Pregnancy.Status.FAILED:
            continue
        if current_preg and preg.id == current_preg.id:
            continue
        mating = preg.breeding_event
        cycles.append(
            {
                'cycle_index': None,
                'is_current': False,
                'label': f'Failed pregnancy · {_iso(preg.confirmed_on) or preg.created_at.date().isoformat()}',
                'outcome': 'failed',
                'mating': BreedingEventSerializer(mating).data if mating else None,
                'pregnancy': PregnancySerializer(preg).data,
                'birth': None,
                'expected_calving_date': _iso(preg.expected_calving_date),
                'calving_date': None,
            }
        )

    # Matings not linked to a pregnancy already shown
    shown_event_ids = set()
    for c in cycles:
        mid = (c.get('mating') or {}).get('id')
        if mid:
            shown_event_ids.add(mid)
    for event in events:
        if event.id in shown_event_ids:
            continue
        cycles.append(
            {
                'cycle_index': None,
                'is_current': False,
                'label': f'Service · {event.mating_date.isoformat()}',
                'outcome': 'service',
                'mating': BreedingEventSerializer(event).data,
                'pregnancy': None,
                'birth': None,
                'expected_calving_date': None,
                'calving_date': None,
            }
        )

    return {
        **summary,
        'cycles': cycles,
        'event_count': len(events),
        'pregnancy_count': len(pregnancies),
        'birth_count': len(births),
    }
