"""Versioned Archipelago gameplay settings shared by the world and client."""
from .mission_data import MISSION_SETS, BY_ID

DEFAULTS = dict(victory_goal='all_sets', goal_set_count=1, goal_final_set='usa',
                power_outage_seconds=30, production_shutdown_seconds=20,
                cash_theft_percent=25, ability_cooldown_percent=100,
                death_link_grace_seconds=0, progress_tracker=True)
RANGES = dict(goal_set_count=(1, 12), power_outage_seconds=(5, 180),
              production_shutdown_seconds=(5, 180), cash_theft_percent=(1, 100),
              ability_cooldown_percent=(25, 300), death_link_grace_seconds=(0, 300))


def validate_options(values, missions):
    if not isinstance(values, dict) or set(values) != set(DEFAULTS):
        raise ValueError('Missing or unknown gameplay options.')
    for key, (lo, hi) in RANGES.items():
        if type(values[key]) is not int or not lo <= values[key] <= hi:
            raise ValueError(f'Invalid {key}; expected {lo}-{hi}.')
    if type(values['progress_tracker']) is not bool:
        raise ValueError('Invalid progress tracker option.')
    if values['victory_goal'] not in ('all_sets', 'set_count', 'final_mission'):
        raise ValueError('Invalid victory goal.')
    if not isinstance(values['goal_final_set'], str) or values['goal_final_set'] not in MISSION_SETS:
        raise ValueError('Invalid final mission set.')
    sets = {m['campaign'] for m in missions}
    if values['victory_goal'] == 'set_count' and values['goal_set_count'] > len(sets):
        raise ValueError('Goal set count exceeds the enabled mission sets.')
    if values['victory_goal'] == 'final_mission' and values['goal_final_set'] not in sets:
        raise ValueError('Enable the campaign containing the selected final mission.')
    return dict(values)


def completed_sets(missions, completed):
    return {key for key in {m['campaign'] for m in missions}
            if all(m['id'] in completed for m in missions if m['campaign'] == key)}


def final_mission(missions, key):
    # Shared mission table is ordered in story/challenge battle order.
    return [m for m in missions if m['campaign'] == key][-1]


def goal_reached(options, missions, completed):
    if not missions:
        return False
    goal = options['victory_goal']
    if goal == 'final_mission':
        return final_mission(missions, options['goal_final_set'])['id'] in completed
    done = completed_sets(missions, completed)
    needed = options['goal_set_count'] if goal == 'set_count' else len({m['campaign'] for m in missions})
    return len(done) >= needed


def progress_lines(missions, completed, locations, page):
    sets = [key for key in MISSION_SETS if any(m['campaign'] == key for m in missions)]
    earned = len(set(completed) & set(locations))
    overall = f'Checks {earned}/{len(locations)} | Remaining {len(locations)-earned} | Sets {len(completed_sets(missions, completed))}/{len(sets)}'
    if not sets:
        return [overall, 'No mission sets selected.', '', '', '', '']
    key = sets[page % len(sets)]
    selected = [m for m in missions if m['campaign'] == key]
    lines = [overall, f'{MISSION_SETS[key]["label"]}: {sum(m["id"] in completed for m in selected)}/{len(selected)} missions complete']
    entries = [f'Mission {int(m["mission"].removeprefix("mission"))}: {"DONE" if m["id"] in completed else "Pending"}' for i, m in enumerate(selected)]
    lines += ['    |    '.join(entries[i:i+2]) for i in range(0, 8, 2)]
    return lines


def progress_view(missions, completed, locations, page, unlocked_sets):
    """Reachability follows the world's set-unlock rules, not mission order."""
    sets = [key for key in MISSION_SETS if any(m['campaign'] == key for m in missions)]
    remaining = set(locations) - set(completed)
    key = sets[page % len(sets)] if sets else None
    selected = [m for m in missions if m['campaign'] == key]
    return dict(earned=len(set(completed) & set(locations)), total=len(locations),
                remaining=len(remaining), in_logic=sum(BY_ID[i]['campaign'] in unlocked_sets for i in remaining),
                done_sets=len(completed_sets(missions, completed)), total_sets=len(sets),
                title=MISSION_SETS[key]['label'] + ':' if key else 'No mission sets selected.',
                set_progress=f'{sum(m["id"] in completed for m in selected)}/{len(selected)} missions complete',
                missions=[(f'Mission {int(m["mission"].removeprefix("mission"))}:',
                           'DONE' if m['id'] in completed else 'Pending',
                           'complete' if m['id'] in completed else 'available' if key in unlocked_sets else 'locked')
                          for m in selected])
