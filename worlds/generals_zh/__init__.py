from .Options import DeathLinkGraceEnabled, VictoryGoal, GoalSetCount, GoalFinalSet, PowerOutageSeconds, ProductionShutdownSeconds, CashTheftPercent, AbilityCooldownPercent, DeathLinkGraceSeconds, StartingBuilders, StartingAbilities, StartingGeneralsPoints
from .game_options import DEFAULTS, validate_options, goal_reached, final_mission
from BaseClasses import Item, ItemClassification, Location, Region, Tutorial
from Options import OptionGroup
from .Options import ZeroHourOptions, USACampaign, ChinaCampaign, GLACampaign, DisableUnitOnlyMissions, GeneralsChallengeCampaigns, ProgressiveStartingCash, PowerOutageTraps, ZeroHourDeathLink
from worlds.AutoWorld import WebWorld, World
from .Options import StartingMissionSets, StartingSetCount, DeathLinkMode, MissionCompletionChecks, SetCompletionChecks
from .Options import Reinforcements, SupplyDrops, TrapsEnabled, TrapPercentage, PowerOutageWeight, CashTheftWeight, ProductionShutdownWeight, SellRandomBuildingWeight
from .trap_pool import make_filler_pool, TRAP_NAMES, FILLER_NAMES
from .Options import MissionReportWeight, SupplyDropWeight, ReinforcementsWeight
from collections import Counter
from .mission_data import CONSUMABLE_CONFIG, REINFORCEMENTS_ID, SUPPLY_DROP_ID, CASH_THEFT_ID, PRODUCTION_SHUTDOWN_ID, SELL_BUILDING_ID
from .mission_data import MISSION_SETS, SET_ITEMS, ALL_CHECKS, with_set_bonuses, choose_starting_sets, selected_sets
from .mission_data import ALL_BUILDER_ITEMS
from .Options import GeneralBuilderUnlocks, RevealMinimap, CarpetBomb, PatriotAirdrop, SellBuildingRefund
from .mission_data import ABILITY_ITEMS, ABILITY_CONFIG, GENERALS_ITEMS, GENERALS_POINT_NAME, GENERALS_POINT_ID, GENERALS_CONFIG
from .Options import ProgressiveGeneralsPowers, GeneralsPointItems

from .mission_data import CAMPAIGNS, GAME, ITEM_ID, ITEM_NAME, MISSIONS, PROTOCOL_VERSION, BUILDER_ITEMS, ALL_MISSIONS, CHALLENGE_NAMES, select_missions, EFFECT_ITEMS, EFFECT_CONFIG, CASH_ITEM_ID, POWER_TRAP_ID, CASH_ITEM_NAME, POWER_TRAP_NAME


class ZeroHourItem(Item):
    game = GAME


class ZeroHourLocation(Location):
    game = GAME


class ZeroHourWeb(WebWorld):
    option_groups = [OptionGroup("Victory", [VictoryGoal, GoalSetCount, GoalFinalSet]), OptionGroup("Starting Unlocks", [StartingBuilders, StartingAbilities, StartingGeneralsPoints]), OptionGroup("Game Balance", [PowerOutageSeconds, ProductionShutdownSeconds, CashTheftPercent, AbilityCooldownPercent]), OptionGroup("Campaign Checks", [USACampaign, ChinaCampaign, GLACampaign, DisableUnitOnlyMissions, GeneralsChallengeCampaigns]),
                     OptionGroup("Check Counts", [MissionCompletionChecks, SetCompletionChecks]),
                     OptionGroup("Permanent Unlocks", [GeneralBuilderUnlocks, RevealMinimap, CarpetBomb, PatriotAirdrop, ProgressiveGeneralsPowers, GeneralsPointItems]),
                     OptionGroup("Helpful Items", [ProgressiveStartingCash]),
                     OptionGroup("Useful Item Filler", [MissionReportWeight, SupplyDropWeight, ReinforcementsWeight]),
                     OptionGroup("Traps", [TrapsEnabled, TrapPercentage, PowerOutageWeight, CashTheftWeight, ProductionShutdownWeight, SellRandomBuildingWeight, SellBuildingRefund]),
                     OptionGroup("Starting Mission Sets", [StartingMissionSets, StartingSetCount]),
                     OptionGroup("Deathlink", [ZeroHourDeathLink, DeathLinkMode, DeathLinkGraceEnabled, DeathLinkGraceSeconds])]
    tutorials = [Tutorial("Setup", "Set up Zero Hour campaign checks and the cross-faction builder unlocks.",
                          "English", "setup_en.md", "setup/en", ["Ben"])]


class ZeroHourWorld(World):
    """Complete selected story and Generals Challenge battles to send checks.

    Three builder items enable their units at all stock faction Command Centers.
    """

    game = GAME
    options_dataclass = ZeroHourOptions
    options: ZeroHourOptions
    web = ZeroHourWeb()
    required_client_version = (0, 6, 7)
    item_name_to_id = {ITEM_NAME: ITEM_ID, **{name: code for code, name in {**ALL_BUILDER_ITEMS, **ABILITY_ITEMS, **GENERALS_ITEMS, **EFFECT_ITEMS, **SET_ITEMS}.items()}}
    location_name_to_id = {mission["name"]: mission["id"] for mission in ALL_CHECKS}
    location_name_groups = {
        campaign: {m["name"] for m in MISSIONS if m["campaign"] == campaign.lower()}
        for campaign in CAMPAIGNS
    }

    def generate_early(self):
        obsolete = [name for name in ('power_outage_traps', 'cash_thefts', 'production_shutdowns')
                    if getattr(self.options, name).value]
        if obsolete:
            raise ValueError("Old fixed trap counts are no longer supported: " + ', '.join(obsolete)
                             + ". Recreate your YAML using Enable Traps, trap_percentage and the three trap weights.")
        old_counts = [name for name in ('reinforcements', 'supply_drops')
                      if getattr(self.options, name).value]
        if old_counts:
            raise ValueError("Fixed helpful item counts are no longer supported: " + ', '.join(old_counts)
                             + ". Recreate your YAML using the Useful Item Filler weights.")
        self.enabled_campaigns = [name for name in CAMPAIGNS
                                 if getattr(self.options, name.lower() + "_campaign").value]
        self.selected_challenges, self.starting_sets = choose_starting_sets(
            self.enabled_campaigns, self.options.generals_challenge_campaigns.value,
            self.options.starting_mission_sets.value, self.options.starting_set_count.value, self.random,
            (self.options.goal_final_set.current_key,) if self.options.victory_goal.current_key == "final_mission" and self.options.goal_final_set.current_key in CHALLENGE_NAMES else ())
        self.selected_missions = select_missions(self.enabled_campaigns,
                                                bool(self.options.disable_unit_only_missions.value),
                                                self.selected_challenges)
        self.selected_locations = with_set_bonuses(self.selected_missions, self.options.mission_completion_checks.value, self.options.set_completion_checks.value)
        self.sets = selected_sets(self.selected_missions)
        self.ability_items = {item: name for item, name in ABILITY_ITEMS.items()
                              if getattr(self.options, name.lower().replace(' ', '_')).value}
        self.builder_items = ALL_BUILDER_ITEMS if self.options.general_builder_unlocks.value else BUILDER_ITEMS
        self.game_options = validate_options({key: (getattr(self.options, key).current_key if key in ('victory_goal', 'goal_final_set') else True if key == 'progress_tracker' else getattr(self.options, key).value) for key in DEFAULTS}, self.selected_missions)
        if not self.options.death_link_grace_enabled.value:
            self.game_options['death_link_grace_seconds'] = 0
        self.starting_unlocks = set(self.options.starting_builders.value) | set(self.options.starting_abilities.value)
        if not self.starting_unlocks <= set(self.builder_items.values()) | set(self.ability_items.values()):
            raise ValueError('Enable every selected starting builder and ability.')
        points = self.options.starting_generals_points.value
        if points and (not self.options.progressive_generals_powers.value or points > self.options.generals_point_items.value):
            raise ValueError('Starting Generals Points require progressive powers and cannot exceed the configured item count.')


    def create_regions(self):
        menu = Region("Menu", self.player, self.multiworld)
        self.multiworld.regions.append(menu)
        for campaign in (*self.enabled_campaigns, *self.selected_challenges):
            label = CHALLENGE_NAMES.get(campaign, campaign)
            region = Region(f"{label} Campaign", self.player, self.multiworld)
            region.locations = [
                ZeroHourLocation(self.player, m["name"], m["id"], region)
                for m in self.selected_locations if m["campaign"] == campaign.lower()
            ]
            item = MISSION_SETS[campaign.lower()]['item_name']
            menu.connect(region, rule=lambda state, item=item: state.has(item, self.player))
            self.multiworld.regions.append(region)

    def create_items(self):
        points = self.options.generals_point_items.value if self.options.progressive_generals_powers.value else 0
        points -= self.options.starting_generals_points.value
        cash = self.options.progressive_starting_cash.value
        pool_sets = [key for key in self.sets if key not in self.starting_sets]
        remaining = len(self.selected_locations) - len(self.builder_items) - len(pool_sets) - cash - len(self.ability_items) - points + len(self.starting_unlocks)
        if remaining < 0:
            raise ValueError(f"{len(self.selected_locations)} checks cannot hold {len(self.builder_items)} builders, {cash + len(self.ability_items)} helpful items, {points} Generals Point items and {len(pool_sets)} set unlocks. Increase check counts, reduce item counts, disable general builders, or enable more campaigns.")
        filler = make_filler_pool(remaining, bool(self.options.traps_enabled.value),
            self.options.trap_percentage.value, (self.options.power_outage_weight.value,
            self.options.cash_theft_weight.value, self.options.production_shutdown_weight.value, self.options.sell_random_building_weight.value), self.random,
            (self.options.mission_report_weight.value, self.options.supply_drop_weight.value, self.options.reinforcements_weight.value))
        self.filler_counts = Counter(filler)
        for name in sorted(self.starting_unlocks):
            self.multiworld.push_precollected(self.create_item(name))
        for _ in range(self.options.starting_generals_points.value):
            self.multiworld.push_precollected(self.create_item(GENERALS_POINT_NAME))
        for key in self.starting_sets:
            self.multiworld.push_precollected(self.create_item(MISSION_SETS[key]['item_name']))
        self.multiworld.itempool.extend(self.create_item(MISSION_SETS[key]['item_name']) for key in pool_sets)
        self.multiworld.itempool += [self.create_item(name) for name in filler]
        self.multiworld.itempool += [self.create_item(GENERALS_POINT_NAME) for _ in range(points)]
        self.multiworld.itempool += [self.create_item(CASH_ITEM_NAME) for _ in range(cash)]
        self.multiworld.itempool.extend(self.create_item(name) for name in self.builder_items.values() if name not in self.starting_unlocks)
        self.multiworld.itempool.extend(self.create_item(name) for name in self.ability_items.values() if name not in self.starting_unlocks)

    def create_item(self, name):
        code = self.item_name_to_id[name]
        classification = (ItemClassification.progression if code in SET_ITEMS else
                          ItemClassification.trap if code in (POWER_TRAP_ID, CASH_THEFT_ID, PRODUCTION_SHUTDOWN_ID, SELL_BUILDING_ID) else
                          ItemClassification.useful if code in ALL_BUILDER_ITEMS or code in GENERALS_ITEMS or code in ABILITY_ITEMS or code == CASH_ITEM_ID else ItemClassification.filler)
        return ZeroHourItem(name, classification, code, self.player)

    def get_filler_item_name(self):
        return ITEM_NAME

    def set_rules(self):
        # Each enabled set is playable with its unlock. Model the selected goal's
        # reachable missions; actual completion is reported by the live client.
        self.multiworld.completion_condition[self.player] = lambda state: goal_reached(
            self.game_options, self.selected_missions,
            {m['id'] for m in self.selected_missions if state.has(MISSION_SETS[m['campaign']]['item_name'], self.player)})

    def fill_slot_data(self):
        return {"protocol_version": PROTOCOL_VERSION, "goal": "all_selected_missions", "game_options": self.game_options,
                "unit_unlocks": list(self.builder_items.values()),
                "builder_scope": "campaign_and_challenge_command_centers",
                "builder_menu": True,
                "progressive_generals_powers": bool(self.options.progressive_generals_powers.value),
                "generals_point_items": self.options.generals_point_items.value,
                "generals_points": GENERALS_CONFIG,
                "abilities": ABILITY_CONFIG,
                "ability_unlocks": list(self.ability_items.values()),
                "general_builder_unlocks": bool(self.options.general_builder_unlocks.value),
                "effects": EFFECT_CONFIG,
                "consumables": CONSUMABLE_CONFIG,
                "sell_random_building": True,
                "sell_building_refund": self.options.sell_building_refund.current_key,
                "death_link": bool(self.options.death_link.value),
                "death_link_mode": self.options.death_link_mode.current_key,
                "mission_set_unlocks": {key: MISSION_SETS[key]['item_id'] for key in self.sets},
                "starting_sets": self.starting_sets,
                "mission_completion_checks": self.options.mission_completion_checks.value,
                "set_completion_checks": self.options.set_completion_checks.value,
                "enabled_campaigns": self.enabled_campaigns,
                "disable_unit_only_missions": bool(self.options.disable_unit_only_missions.value),
                "selected_challenges": self.selected_challenges,
                "location_ids": sorted(m["id"] for m in self.selected_locations)}

    def write_spoiler(self, spoiler_handle):
        spoiler_handle.write(f"\nChecks per mission: {self.options.mission_completion_checks.value}; per completed set: {self.options.set_completion_checks.value}\n")
        spoiler_handle.write("\nZero Hour selected Generals Challenge campaigns:\n")
        spoiler_handle.write(", ".join(CHALLENGE_NAMES[c] for c in self.selected_challenges) or "None")
        spoiler_handle.write('\nStarting sets: ' + ', '.join(MISSION_SETS[k]['label'] for k in self.starting_sets))
        spoiler_handle.write(f"\nMission victories: {len(self.selected_missions)}; total checks with set bonuses: {len(self.selected_locations)}\n")
        spoiler_handle.write('Filler/trap pool: ' + ', '.join(
            f'{name}: {self.filler_counts[name]}' for name in (*FILLER_NAMES, *TRAP_NAMES)) + '\n')
