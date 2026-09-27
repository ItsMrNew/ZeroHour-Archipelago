"""Permanent builder choices, shared by the native menu and Command Centers."""
from .builders import BuilderUnlock, MENUS
from .mission_data import BUILDER_CATALOG, ALL_BY_CAMPAIGN_MISSION

FAMILIES = ('usa', 'china', 'gla')
GENERAL_MENUS = dict(MENUS)
for prefix in ('airf', 'lazr', 'supw'):
    GENERAL_MENUS[prefix + '_americacommandcentercommandset'] = (0, 2, 10)
for prefix in ('infa', 'nuke', 'tank'):
    for suffix in ('', 'upgrade'):
        GENERAL_MENUS[prefix + '_chinacommandcentercommandset' + suffix] = (10, 0, 12)
for prefix in ('demo', 'slth', 'chem'):
    GENERAL_MENUS[prefix + '_glacommandcentercommandset'] = (1, 9, 0)
GENERAL_MENUS['demo_glacommandcentercommandsetupgrade'] = (1, 9, 0)


def choices(owned, preferences):
    result = {}
    for family in FAMILIES:
        available = [item for item, entry in BUILDER_CATALOG.items()
                     if entry[1] == family and item in owned]
        preferred = preferences.get(family)
        result[family] = (preferred if preferred in available else None) if family in preferences else next(iter(available), None)
    return result


class SelectableBuilders(BuilderUnlock):
    menu_defs = GENERAL_MENUS
    button_names = tuple(entry[2] for entry in BUILDER_CATALOG.values())
    mission_lookup = ALL_BY_CAMPAIGN_MISSION

    def __init__(self, game):
        super().__init__(game)
        self.selected = {}

    def context(self):
        context = super().context()
        if context and context[0]:
            logic = context[0]
            if any(self.game.read(logic + 0x51, 2)) or self.game.read(logic + 0x64, 1) != b'\0':
                return None  # Wait until native map/save loading has finished.
        return context

    def desired_button(self, index, owned, buttons):
        selected = self.selected.get(FAMILIES[index])
        return buttons[BUILDER_CATALOG[selected][2]] if selected in owned else 0

    def desired_field(self, key, value, index, owned, buttons):
        if self.selected.get(FAMILIES[index]) not in owned:
            # OFF removes our override, restoring this particular Command
            # Center's native builder (and any mission-specific restriction).
            # Foreign slots return to their original empty/rally buttons.
            return self.edits.get(key, (value, value))[0]
        return self.desired_button(index, owned, buttons)

    def allowed(self, key, value, buttons):
        _, name, slot, *_ = key
        family = FAMILIES[self.menu_defs[name].index(slot)]
        names = {entry[2] for entry in BUILDER_CATALOG.values() if entry[1] == family}
        if 'chinacommandcenter' in name and slot == 12:
            names.add('command_setrallypoint')
        return value == 0 or value in {buttons[n] for n in names if n in buttons}

    def apply_selection(self, owned, preferences):
        self.selected = choices(owned, preferences)
        status = self.apply(owned)
        if status.startswith('Builders unlocked:'):
            names = ', '.join(BUILDER_CATALOG[i][0] for i in self.selected.values() if i is not None) or 'none'
            return f'Builders selected: {names}. Reselect your Command Center.'
        return status.replace('stock campaign mission', 'campaign or Generals Challenge mission')
