from dataclasses import dataclass

from Options import DefaultOnToggle, Toggle, Range, Choice, OptionSet, PerGameCommonOptions, DeathLink, Visibility
from .mission_data import MISSION_SETS, ALL_BUILDER_ITEMS, ABILITY_ITEMS, GENERALS_POINTS_MAX, GENERALS_POINTS_LIMIT


class ProgressiveGeneralsPowers(Toggle):
    """Replace combat-earned Generals points with Progressive Generals Point items.
    Each received item adds one point to your budget in every mission. Purchases
    are separate for each mission. Rank follows total received points (ranks 1-5
    at 1, 2, 3, 4 and 7 points), not XP or your unspent balance. Mission rank caps
    and hidden powers still apply. Scripted free powers are retained.
    """
    display_name = "Progressive Generals Powers"


class GeneralsPointItems(Range):
    """Number of Progressive Generals Point items when Progressive Generals Powers
    is enabled. Default 18 covers the largest stock powers menu (China/Infantry).
    Up to 10 extra items can be included. Enable more mission sets or reduce other
    items if the selected checks cannot hold this many items.
    """
    display_name = "Progressive Generals Point Items"
    range_start = 0
    range_end = GENERALS_POINTS_LIMIT
    default = GENERALS_POINTS_MAX


class ZeroHourDeathLink(DeathLink):
    """Send a DeathLink when a stock story or Generals Challenge mission fails.
    Received DeathLinks restart the active mission. Links received in menus,
    loading screens or after victory/defeat are ignored. Default: disabled.
    """


class DeathLinkMode(Choice):
    """Option 1, Full Restart: normal mission restart; you must re-watch the opening intro.
    Option 2, Quick Reset (experimental): watch the intro once, then restore an automatic
    post-intro checkpoint on received DeathLinks. Keep the client connected before starting
    the mission. Without a checkpoint, uses Option 1. Only applies when DeathLink is enabled.
    """
    display_name = "DeathLink Restart Mode"
    option_full_restart = 0
    option_quick_reset = 1
    default = 0


class USACampaign(DefaultOnToggle):
    """Count USA campaign mission victories as checks."""
    display_name = "USA Campaign"


class ChinaCampaign(DefaultOnToggle):
    """Count China campaign mission victories as checks."""
    display_name = "China Campaign"


class GLACampaign(DefaultOnToggle):
    """Count GLA campaign mission victories as checks."""
    display_name = "GLA Campaign"


class DisableUnitOnlyMissions(Toggle):
    """Remove USA Mission 3 and GLA Mission 4 from checks. Does not prevent playing them."""
    display_name = "Disable Unit Only Missions"


class GeneralsChallengeCampaigns(Range):
    """Number of distinct playable-general campaigns selected by the seed.
    Each selected campaign includes seven or eight battle victories, using your checks-per-mission setting.
    Selected generals are listed in the spoiler and client. Zero disables challenge checks.
    """
    display_name = "Generals Challenge Campaigns"
    range_start = 0
    range_end = 9
    default = 0


class MissionCompletionChecks(Range):
    """Checks sent for each completed story or Generals Challenge mission.
    Each mission awards its checks once, regardless of replays or difficulty.
    """
    display_name = "Checks per Mission"
    range_start = 1
    range_end = 10
    default = 1


class SetCompletionChecks(Range):
    """Additional checks for completing every included mission in a set.
    Excluded unit-only missions are not required. Zero disables the set bonus.
    Each set awards its bonus once.
    """
    display_name = "Checks per Completed Set"
    range_start = 0
    range_end = 10
    default = 5


class ProgressiveStartingCash(Range):
    """Number of Progressive Starting Cash items in the pool. Each gives $5,000
    on receipt and adds $5,000 to future fresh mission starts. Keep the client open
    through mission loading. Saved-game loads do not receive another start bonus.
    """
    display_name = "Progressive Starting Cash Items"
    range_start = 0
    range_end = 10
    default = 0



class PowerOutageTraps(Range):
    """Number of Power Outage Traps in the pool. Each sets reported power output
    to zero for 30 simulation seconds. Additional traps extend the timer.
    """
    display_name = "Power Outage Traps"
    range_start = 0
    range_end = 10
    default = 0
    visibility = Visibility.none  # recognized only to report obsolete YAMLs


class StartingMissionSets(OptionSet):
    """Choose specific starting sets by label, or leave empty for random choices.
    Remaining starting slots are filled randomly. Chosen story campaigns must be
    enabled; chosen challenge generals are included in the selected challenge count.
    """
    display_name = "Starting Mission Sets"
    valid_keys = {s['label'] for s in MISSION_SETS.values()}
    default = frozenset()


class Reinforcements(Range):
    """Number of Reinforcements items. With client 0.13.2+, each deploys three CIA
    Agents and one Heroic (level 3) Humvee containing five Heroic Missile Defenders,
    regardless of faction. Arrives near a friendly Command Center or ground army.
    Requires clear, revealed ground. One-time effect; does not unlock training.
    """
    display_name = "Reinforcements Items"
    range_start = 0
    range_end = 10
    default = 0
    visibility = Visibility.none  # obsolete counts; fail with migration guidance



class SupplyDrops(Range):
    """Number of Supply Drop items. Each grants $5,000 once during an active
    mission. Items received outside gameplay wait until you have control.
    Unlike Progressive Starting Cash, these do not increase future starting money.
    """
    display_name = "Supply Drop Items"
    range_start = 0
    range_end = 10
    default = 0
    visibility = Visibility.none  # obsolete counts; fail with migration guidance



class CashThefts(Range):
    """Number of Cash Theft traps. Each removes 25% of your current cash when
    applied, with no cap. The amount stolen is rounded down to whole dollars.
    Multiple traps each take 25% of the remaining balance.
    """
    display_name = "Cash Theft Traps"
    range_start = 0
    range_end = 10
    default = 0
    visibility = Visibility.none


class ProductionShutdowns(Range):
    """Number of Production Shutdown traps. Each pauses your unit training for
    20 simulation seconds, retaining queued units. More traps extend the timer.
    Enemy production and upgrade research are unaffected. Cleared by mission reset.
    """
    display_name = "Production Shutdown Traps"
    range_start = 0
    range_end = 10
    default = 0
    visibility = Visibility.none


class TrapsEnabled(Toggle):
    """Allocate remaining filler slots to traps. Unlocks, builders and
    Generals Point items are placed first. Disabled means no random traps.
    """
    display_name = "Enable Traps"


class MissionReportWeight(Range):
    """Relative chance of Mission Report in filler slots left after traps.
    No gameplay effect. Zero (default) excludes it.
    """
    display_name = "Mission Report Filler Weight"
    range_start = 0
    range_end = 100
    default = 0


class SupplyDropWeight(Range):
    """Relative chance of a $5,000 Supply Drop in filler slots left after traps.
    One-time grant, after player control returns; does not increase future starting money. Zero excludes it.
    """
    display_name = "Supply Drop Filler Weight"
    range_start = 0
    range_end = 100
    default = 50


class ReinforcementsWeight(Range):
    """Relative chance of Reinforcements in filler slots left after traps.
    Three CIA Agents and a Heroic (level 3) Humvee with five Heroic Missile Defenders, for any faction. Arrives near your Command Center or army on clear, revealed ground. Activates automatically; does not unlock training. Zero excludes it.
    """
    display_name = "Reinforcements Filler Weight"
    range_start = 0
    range_end = 100
    default = 50


class ProductionSurgeWeight(Range):
    """Relative chance of Production Surge in filler slots left after traps.
    Doubles your unit training speed for 120 seconds of player control. Extra copies
    extend the duration; they do not increase speed further. Research is unaffected.
    Waits for an active mission. Reset/load clears active boosts. Zero excludes it.
    """
    display_name = "Production Surge Filler Weight"
    range_start = 0
    range_end = 100
    default = 50


class ConstructionBoostWeight(Range):
    """Relative chance of Construction Boost in filler slots left after traps.
    Your dozers and workers construct buildings at twice normal speed for 120 seconds
    of player control. Extra copies extend the duration. Normal builder and power
    requirements still apply. Reset/load clears active boosts. Zero excludes it.
    """
    display_name = "Construction Boost Filler Weight"
    range_start = 0
    range_end = 100
    default = 50


class TrapPercentage(Range):
    """Percentage of remaining slots allocated to traps after unlocks, builders
    and Progressive Starting Cash items. Default 50 splits traps and weighted useful filler
    equally. Traps round down; an odd extra slot goes to filler. Filler weights
    choose helpful items or Mission Reports. 100 uses only traps.
    Only applies with traps enabled; disabling traps uses only filler weights.
    """
    display_name = "Remaining Pool Allocated to Traps (%)"
    range_start = 0
    range_end = 100
    default = 50


class PowerOutageWeight(Range):
    """Relative chance of Power Outage Trap among traps. Duration is set by Power Outage Duration. Zero excludes it; weight 3 is three times as likely as weight 1.
    Only applies with traps enabled. Actual counts vary with the seed.
    """
    display_name = "Power Outage Trap Weight"
    range_start = 0
    range_end = 100
    default = 50


class CashTheftWeight(Range):
    """Relative chance of Cash Theft among traps. The Cash Theft Percentage setting controls
    the loss of current cash, with no cap. Zero excludes it; higher weights make it more common.
    Only applies with traps enabled. Actual counts vary with the seed.
    """
    display_name = "Cash Theft Weight"
    range_start = 0
    range_end = 100
    default = 50


class ProductionShutdownWeight(Range):
    """Relative chance of Production Shutdown among traps. Each pauses unit
    training for the configured Production Shutdown Duration. Zero excludes it; higher weights make it more common.
    Only applies with traps enabled. Actual counts vary with the seed.
    """
    display_name = "Production Shutdown Weight"
    range_start = 0
    range_end = 100
    default = 50


class SellRandomBuildingWeight(Range):
    """Relative chance of Sell Random Building. Sells one random completed,
    eligible building you own using the selected sale refund mode. Waits for player control.
    Skips unsellable buildings; no eligible building consumes the trap harmlessly.
    Zero excludes it. Only applies with traps enabled.
    """
    display_name = "Sell Random Building Weight"
    range_start = 0
    range_end = 100
    default = 50


class GeneralBuilderUnlocks(DefaultOnToggle):
    """Add nine permanent general-specific Dozer/Worker unlocks to the pool,
    alongside the three standard builders. Use the in-game Archipelago menu to
    choose one unlocked builder per faction. Works in campaigns and challenges.
    Requires room for twelve builder items; enable more mission sets if needed.
    """
    display_name = "General Builder Unlocks"


class StartingSetCount(Range):
    """Number of mission sets unlocked at the start, including your specific choices.
    Limited to the number of enabled sets. At least one set always starts unlocked.
    """
    display_name = "Starting Set Count"
    range_start = 1
    range_end = 12
    default = 1


class RevealMinimap(DefaultOnToggle):
    """Add one permanent Reveal Minimap unlock. Use it in the Archipelago Abilities
    tab for 15 seconds of vision, with a three-minute simulation-time cooldown.
    Cooldowns carry through DeathLink resets. Supply Drop stays automatic.
    """
    display_name = "Reveal Minimap Unlock"


class CarpetBomb(DefaultOnToggle):
    """Add one permanent Carpet Bomb unlock. Use the Abilities tab, then click terrain
    for the USA Air Force strike, regardless of faction. Right-click cancels targeting.
    Four-minute simulation-time cooldown, retained through DeathLink resets.
    """
    display_name = "Carpet Bomb Unlock"


class SellBuildingRefund(Choice):
    """Normal Refund uses the game's normal sale refund and animation.
    No Refund removes the selected building immediately after native sale cleanup,
    returning no money, including refunds for cancelled production.
    Applies to Sell Random Building traps only.
    """
    display_name = "Building Sale Refund"
    option_normal_refund = 0
    option_no_refund = 1
    default = 0


class PatriotAirdrop(DefaultOnToggle):
    """Add one permanent Patriot Airdrop unlock. Target clear ground from the
    Archipelago Abilities tab to deliver three USA Patriot Missile Systems by
    cargo plane and parachute, for any faction. Five-minute cooldown, retained
    through DeathLink resets. Airdropped Patriots use no power and retain standard
    Patriot health and weapons. The client installs an additive ability definition;
    restart Zero Hour after its first installation.
    """
    display_name = "Patriot Airdrop Unlock"


class EmergencyRepair(DefaultOnToggle):
    """Add one permanent Emergency Repair unlock. The stock Level 3 ability
    instantly restores up to 300 HP to each eligible friendly vehicle within
    radius 100. Four-minute cooldown (before the ability cooldown multiplier),
    retained across missions and DeathLink resets. No Generals points required.
    """
    display_name = "Emergency Repair Unlock"


class VictoryGoal(Choice):
    """Win by completing all enabled sets, a chosen number of sets, or the last
    mission of a selected set. Other checks remain available after victory."""
    display_name = "Victory Goal"
    option_all_sets = 0
    option_set_count = 1
    option_final_mission = 2
    default = 0


class GoalFinalSet(Choice):
    """For Final Mission, complete the last battle of this set. Enable its story
    campaign or enough challenge campaigns to include the selected general."""
    display_name = "Final Mission Set"
    option_usa = 0
    option_gla = 1
    option_china = 2
    option_challenge_0 = 3
    option_challenge_1 = 4
    option_challenge_2 = 5
    option_challenge_3 = 6
    option_challenge_4 = 7
    option_challenge_5 = 8
    option_challenge_6 = 9
    option_challenge_7 = 10
    option_challenge_8 = 11
    default = 0


class GoalSetCount(Range):
    """Number of enabled sets to complete when using the Set Count goal."""
    display_name = "Sets Required for Victory"
    range_start = 1
    range_end = 12
    default = 1


class PowerOutageSeconds(Range):
    """Simulation seconds per Power Outage Trap. Repeated traps extend it."""
    display_name = "Power Outage Duration"
    range_start = 5
    range_end = 180
    default = 30


class ProductionShutdownSeconds(Range):
    """Simulation seconds per Production Shutdown. Repeated traps extend it."""
    display_name = "Production Shutdown Duration"
    range_start = 5
    range_end = 180
    default = 20


class CashTheftPercent(Range):
    """Percentage of current cash removed per trap, rounded down, with no cap."""
    display_name = "Cash Theft Percentage"
    range_start = 1
    range_end = 100
    default = 25


class AbilityCooldownPercent(Range):
    """Scale permanent Archipelago ability cooldowns. 100 is normal; 50 is half. Does not change native Generals powers."""
    display_name = "Ability Cooldown (%)"
    range_start = 25
    range_end = 300
    default = 100


class DeathLinkGraceEnabled(Toggle):
    """Enable a grace period after an incoming DeathLink restarts your mission.
    Disabled by default. You can also override this locally in the in-game menu."""
    display_name = "Enable DeathLink Grace Period"


class DeathLinkGraceSeconds(Range):
    """Ignore incoming DeathLinks for this many seconds of player-controlled gameplay after a DeathLink reset. Only applies when Enable DeathLink Grace Period is on. Mission failures still send links."""
    display_name = "DeathLink Grace Period"
    range_start = 0
    range_end = 300
    default = 30


class StartingGeneralsPoints(Range):
    """Precollect this many of the configured Progressive Generals Point items. Requires progressive powers and cannot exceed the item count."""
    display_name = "Starting Generals Points"
    range_start = 0
    range_end = 28
    default = 0


class StartingBuilders(OptionSet):
    """Start with these builder unlocks instead of placing them in the pool.
    General variants require General Builder Unlocks to be enabled."""
    display_name = "Starting Builders"
    valid_keys = set(ALL_BUILDER_ITEMS.values())
    default = frozenset()


class StartingAbilities(OptionSet):
    """Start with these permanent abilities. Enable each selected ability above.
    Precollected items free their pool slots for filler or traps."""
    display_name = "Starting Abilities"
    valid_keys = set(ABILITY_ITEMS.values())
    default = frozenset()


@dataclass
class ZeroHourOptions(PerGameCommonOptions):
    victory_goal: VictoryGoal
    goal_set_count: GoalSetCount
    goal_final_set: GoalFinalSet
    power_outage_seconds: PowerOutageSeconds
    production_shutdown_seconds: ProductionShutdownSeconds
    cash_theft_percent: CashTheftPercent
    ability_cooldown_percent: AbilityCooldownPercent
    death_link_grace_enabled: DeathLinkGraceEnabled
    death_link_grace_seconds: DeathLinkGraceSeconds
    starting_builders: StartingBuilders
    starting_abilities: StartingAbilities
    starting_generals_points: StartingGeneralsPoints
    mission_completion_checks: MissionCompletionChecks
    set_completion_checks: SetCompletionChecks
    progressive_generals_powers: ProgressiveGeneralsPowers
    generals_point_items: GeneralsPointItems
    reveal_minimap: RevealMinimap
    carpet_bomb: CarpetBomb
    patriot_airdrop: PatriotAirdrop
    emergency_repair: EmergencyRepair
    general_builder_unlocks: GeneralBuilderUnlocks
    usa_campaign: USACampaign
    china_campaign: ChinaCampaign
    gla_campaign: GLACampaign
    disable_unit_only_missions: DisableUnitOnlyMissions
    generals_challenge_campaigns: GeneralsChallengeCampaigns

    progressive_starting_cash: ProgressiveStartingCash
    power_outage_traps: PowerOutageTraps
    reinforcements: Reinforcements
    supply_drops: SupplyDrops
    mission_report_weight: MissionReportWeight
    supply_drop_weight: SupplyDropWeight
    reinforcements_weight: ReinforcementsWeight
    production_surge_weight: ProductionSurgeWeight
    construction_boost_weight: ConstructionBoostWeight
    cash_thefts: CashThefts
    production_shutdowns: ProductionShutdowns
    traps_enabled: TrapsEnabled
    trap_percentage: TrapPercentage
    power_outage_weight: PowerOutageWeight
    cash_theft_weight: CashTheftWeight
    production_shutdown_weight: ProductionShutdownWeight
    sell_random_building_weight: SellRandomBuildingWeight
    sell_building_refund: SellBuildingRefund
    death_link: ZeroHourDeathLink
    death_link_mode: DeathLinkMode
    starting_mission_sets: StartingMissionSets
    starting_set_count: StartingSetCount
