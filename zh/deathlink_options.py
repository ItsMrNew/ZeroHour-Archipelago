"""Local, per-slot overrides for the immutable DeathLink YAML settings."""
DEFAULT_SELECTION = {'mode': 'yaml', 'grace': 'yaml', 'seconds': 30}
MODE_LABELS = {'full_restart': 'Full Restart', 'quick_reset': 'Quick Reset'}


def validate_selection(value):
    if (not isinstance(value, dict) or set(value) != set(DEFAULT_SELECTION)
            or value['mode'] not in ('yaml', 'off', 'full_restart', 'quick_reset')
            or value['grace'] not in ('yaml', 'off', 'on')
            or type(value['seconds']) is not int or not 1 <= value['seconds'] <= 300):
        raise ValueError('Invalid local DeathLink settings.')
    return dict(value)


def resolve(selection, yaml):
    enabled, mode, seconds = yaml
    if selection['mode'] != 'yaml':
        enabled = selection['mode'] != 'off'
        if enabled:
            mode = selection['mode']
    if selection['grace'] != 'yaml':
        seconds = selection['seconds'] if selection['grace'] == 'on' else 0
    return enabled, mode, seconds if enabled else 0


def selected_event(selection, event):
    result = dict(selection)
    if event in (51, 52, 53, 54):
        result['mode'] = {51:'yaml', 52:'off', 53:'full_restart', 54:'quick_reset'}[event]
    elif event in (56, 57, 58):
        result['grace'] = {56:'yaml', 57:'off', 58:'on'}[event]
    elif event in (59, 60):
        result['seconds'] = max(1, min(300, result['seconds'] + (-5 if event == 59 else 5)))
        result['grace'] = 'on'
    return validate_selection(result)


def menu_labels(selection, yaml, remaining):
    enabled, mode, grace = resolve(selection, yaml)
    yaml_enabled, yaml_mode, yaml_grace = yaml
    active = MODE_LABELS[mode] if enabled else 'Off'
    labels = {
        7: ('DeathLink', 1),
        50: (f'YAML: {MODE_LABELS[yaml_mode] if yaml_enabled else "Off"} | Grace: {yaml_grace}s', 0),
        55: (f'Active: {active} | Grace: {grace}s | Left: {(remaining + 29)//30}s', 0),
        59: ('-5 seconds', 1), 60: ('+5 seconds', 1),
        61: (f'Manual grace duration: {selection["seconds"]}s', 0),
        62: ('Quick Reset needs a checkpoint; otherwise the intro replays.', 0),
    }
    for event, value, text in ((51,'yaml','Follow YAML'), (52,'off','Off'),
            (53,'full_restart','Full Restart'), (54,'quick_reset','Quick Reset')):
        labels[event] = (text, 1 | (2 if selection['mode'] == value else 0))
    for event, value, text in ((56,'yaml','Grace: Follow YAML'), (57,'off','Grace: Off'), (58,'on','Grace: On')):
        labels[event] = (text, 1 | (2 if selection['grace'] == value else 0))
    return labels
