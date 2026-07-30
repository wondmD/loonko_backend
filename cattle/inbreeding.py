def get_ancestry_set(cattle, depth=3):
    """
    Recursively extract set of ancestor IDs up to specified depth.
    Returns dict mapping ancestor_id -> list of relation paths (e.g. ['dam.sire']).
    """
    ancestors = {}
    if not cattle or depth <= 0:
        return ancestors

    def traverse(current, path, current_depth):
        if not current or current_depth > depth:
            return
        if current.mother_id:
            m_path = f"{path}.mother" if path else "mother"
            ancestors.setdefault(current.mother_id, []).append(m_path)
            traverse(current.mother, m_path, current_depth + 1)
        if current.father_id:
            f_path = f"{path}.father" if path else "father"
            ancestors.setdefault(current.father_id, []).append(f_path)
            traverse(current.father, f_path, current_depth + 1)

    traverse(cattle, "", 1)
    return ancestors


def check_inbreeding_risk(dam, sire):
    """
    Check if mating dam and sire presents an inbreeding risk based on ancestral overlap.
    """
    if not dam or not sire:
        return {
            'risk_level': 'SAFE',
            'has_conflict': False,
            'message': 'Insufficient ancestry data to detect inbreeding.',
            'common_ancestors': [],
        }

    # Direct parent-offspring check
    if dam.id == sire.id:
        return {
            'risk_level': 'HIGH_RISK_INBREEDING',
            'has_conflict': True,
            'message': 'CRITICAL: Self-mating is impossible.',
            'common_ancestors': [{'id': dam.id, 'tag_id': dam.tag_id, 'relation': 'Self'}],
        }

    if dam.mother_id == sire.id or dam.father_id == sire.id:
        return {
            'risk_level': 'HIGH_RISK_INBREEDING',
            'has_conflict': True,
            'message': f'CRITICAL: {sire.tag_id} is a direct parent of {dam.tag_id}.',
            'common_ancestors': [{'id': sire.id, 'tag_id': sire.tag_id, 'relation': 'Direct Parent'}],
        }

    if sire.mother_id == dam.id or sire.father_id == dam.id:
        return {
            'risk_level': 'HIGH_RISK_INBREEDING',
            'has_conflict': True,
            'message': f'CRITICAL: {dam.tag_id} is a direct parent of {sire.tag_id}.',
            'common_ancestors': [{'id': dam.id, 'tag_id': dam.tag_id, 'relation': 'Direct Parent'}],
        }

    # Full/half sibling check
    if dam.mother_id and dam.mother_id == sire.mother_id:
        return {
            'risk_level': 'HIGH_RISK_INBREEDING',
            'has_conflict': True,
            'message': f'CRITICAL: {dam.tag_id} and {sire.tag_id} share the same dam ({dam.mother.tag_id}).',
            'common_ancestors': [{'id': dam.mother_id, 'tag_id': dam.mother.tag_id, 'relation': 'Shared Dam'}],
        }

    if dam.father_id and dam.father_id == sire.father_id:
        return {
            'risk_level': 'HIGH_RISK_INBREEDING',
            'has_conflict': True,
            'message': f'CRITICAL: {dam.tag_id} and {sire.tag_id} share the same sire ({dam.father.tag_id}).',
            'common_ancestors': [{'id': dam.father_id, 'tag_id': dam.father.tag_id, 'relation': 'Shared Sire'}],
        }

    # 3-Generation Ancestry Overlap Check
    dam_ancestors = get_ancestry_set(dam, depth=3)
    sire_ancestors = get_ancestry_set(sire, depth=3)

    common_ids = set(dam_ancestors.keys()) & set(sire_ancestors.keys())

    if not common_ids:
        return {
            'risk_level': 'SAFE',
            'has_conflict': False,
            'message': 'No common ancestors identified in 3-generation lineage.',
            'common_ancestors': [],
        }

    from .models import Cattle
    common_ancestors_info = []
    for cid in common_ids:
        anc = Cattle.objects.filter(id=cid).first()
        tag = anc.tag_id if anc else f'ID-{cid}'
        dam_paths = dam_ancestors.get(cid, [])
        sire_paths = sire_ancestors.get(cid, [])
        common_ancestors_info.append({
            'id': cid,
            'tag_id': tag,
            'dam_relation': dam_paths,
            'sire_relation': sire_paths,
        })

    return {
        'risk_level': 'MODERATE_WARNING',
        'has_conflict': True,
        'message': f'WARNING: {len(common_ids)} common ancestor(s) found in 3-generation lineage.',
        'common_ancestors': common_ancestors_info,
    }
