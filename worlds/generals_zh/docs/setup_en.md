# Zero Hour â€” campaign selection and Generals Challenge

Use launcher 0.8.0 (Steam preview) and world 0.20.0 with stock English Steam
Zero Hour on Windows. This public number follows internal client 0.21.1;
protocol 17 and item/location IDs are unchanged. EA App, Origin, First Decade,
GeneralsOnline and GenTool/GenPatcher combinations are not validated for this release.
See the repository's compatibility guide:
https://github.com/ItsMrNew/ZeroHour-Archipelago/blob/main/docs/COMPATIBILITY.md
Install the world in Archipelago's `custom_worlds` folder and restart Archipelago.
Generate locally using the player YAML, then host and connect the companion client.
Run the client as administrator if the game runs elevated.

The launcher remembers its connection fields and Light/Dark theme. Initial defaults
are `archipelago.gg:5000`, player `ZeroHour`, and no password; clearing a field restores
its default on the next launch. Progress, DeathLink and Notifications can be opened
from the main menu while connected. Sent/received item names are coloured in both
the launcher log and in-game notifications.

The current world classifies Mission Report, Supply Drop and Reinforcements as filler
(cyan). Install the new world and generate a new seed for Archipelago server/trackers
to use that classification. The updated client also corrects their display colours
for existing rooms; other features do not require a new seed.

## Permanent abilities

Enable `reveal_minimap`, `carpet_bomb`, `patriot_airdrop` and/or `emergency_repair` (all default true) to add one
permanent useful unlock per enabled ability. Use the native Archipelago Abilities
tab during campaigns or Generals Challenges. Reveal Minimap gives 15 seconds of
vision and has a three-minute cooldown. Carpet Bomb uses the Air Force strike:
select it, then click terrain; right-click cancels. Its cooldown is four minutes.
Patriot Airdrop sends a cargo plane with three standard Patriot Missile Systems
in parachutes to the selected drop zone. Its cooldown is five minutes. Airdropped Patriots require no power; normal dozer-built Patriots retain their
standard requirement. Restart the game after the client first installs its additive
Patriot definition. Choose clear ground with room for all three defenses.
Cooldowns use controllable simulation time and persist across DeathLink resets and reconnects.
Patriot delivery is confirmed in USA 1 and China 1; the self-powered variant awaits
live confirmation. Reveal Minimap and Carpet Bomb have player confirmation. Automatic Supply Drop
and Reinforcements retain their previous behavior.

## YAML options

- `usa_campaign`, `china_campaign`, `gla_campaign`: default true. Each includes its
  five story mission victories as checks.
- `disable_unit_only_missions`: default false. Removes USA 3 and GLA 4 from checks.
- `generals_challenge_campaigns`: 0â€“9, default 0. Selects this many distinct playable
  general campaigns, chosen by the seed. Each includes seven or eight battles, using the checks-per-mission setting.
- `progressive_starting_cash`: 0â€“10, default 0. Each copy grants $5,000 immediately
  and adds $5,000 to every future fresh mission start.
- `reinforcements_weight`, `supply_drop_weight`: 0-100 relative weights, default 50 each.
  No fixed counts. Supply Drop grants $5,000 once. Reinforcements deploy three CIA
  Agents and a Heroic Humvee with five Heroic Missile Defenders near your army
  or Command Center on clear, revealed ground; both activate automatically.
- `traps_enabled`: default false. Enable allocating a share of remaining slots to traps.
- `trap_percentage`: 0-100, default 50. After fixed items, split the remaining pool into
  50% traps and 50% weighted useful filler. Traps round down; an odd extra slot
  goes to filler. With traps off, all remaining slots use the filler weights.
- `power_outage_weight`, `cash_theft_weight`, `production_shutdown_weight`,
  `sell_random_building_weight`: 0-100,
  default 50 each. Relative chances among traps; zero excludes that trap. Weights
  of 3:1:0:0 mean 75% Power Outage, 25% Cash Theft and no Shutdown or sale trap. At least one
  positive weight is needed when traps and a positive percentage are enabled.
  Power Outage lasts 30 seconds; Cash Theft takes 25% of current cash without a
  cap; Production Shutdown pauses training for 20 seconds. Sell Random Building
  sells one eligible completed owned building using the selected refund mode; no eligible
  target consumes it harmlessly. Traps wait for player control. Actual counts vary by seed.
- `sell_building_refund`: `normal_refund` (default) uses the normal refund and
  sale animation. `no_refund` removes the building immediately after sale cleanup,
  returning no cash, including cancelled production. Applies only to the sale trap.
- `death_link`: default false. Mission failures send DeathLink; received links
  restart the current stock story/challenge mission, discarding unsaved mission
  progress. Links in menus/loading or after a result are ignored. Remote restarts
  do not echo back. Keep the client connected before the failure.

The release includes **Zero Hour Options.html**, an offline creator with toggles,
sliders, YAML preview, and download. Native Archipelago templates expose the same
settings; web options require a host with this custom world installed. Select at
least one campaign. New settings require generating a new seed.

The client and spoiler list selected generals. All nine add 65 checks; all story
campaigns plus all nine give 140, or 138 with the unit-only exclusion. Same opponent,
different playable general counts separately. Excluded individual missions remain playable within unlocked sets; disabled sets are blocked. The goal is all selected mission checks.

The builder menu works in story campaigns and Generals Challenges. Turn an
active selection OFF to restore the Command Center's native builder, including
its original mission restrictions. General builder unlocks default on. Broader
unit randomization is deferred. Mission sets require unlock items.

USA Air Force Battle 01 has live check confirmation. Keep the client open before
battle victory. Old medals are not imported.

Helpful items, builders and non-starting set unlocks must fit the checks. Traps
replace a percentage of the remaining filler and never displace those items.
Retired fixed-count trap keys must be replaced when regenerating old YAMLs.
Keep the client open through mission loading for
starting bonuses. Loading a save does not re-grant a starting bonus. New receipts
in menus wait for an eligible stock story/challenge mission.

Power output restoration uses the game's timer and preserves building changes.
Cash and the power timer have live confirmation. The client uses a temporary
in-memory hook to invoke the native building/radar brownout on the simulation
thread; blackout and subsequent restoration have live confirmation in USA Mission
1. Resume the game to process a queued
trap. Disconnect and close the launcher (Ctrl+C for the console client); restart
Zero Hour after a forced client close.
Failed/uncertain writes are reported and their
receipts are not replayed automatically, to avoid duplicate grants.

Read the release README for compatibility, progress storage, and diagnostics.

DeathLink is optional. Full Restart replays the opening; Quick Reset restores a
post-intro checkpoint. Both modes have player confirmation. For diagnostics,
use the launchers in the release's **Diagnostics** folder. Test seeds are not bundled.

## Mission set unlocks

By default, each included mission awards one check; completing every included mission in a set
awards five more. USA3/GLA4 do not count toward set completion when excluded.
`starting_mission_sets` is a list of labels such as `[USA, GLA Stealth]`; `[]`
means random. `starting_set_count` is 1-12 (default 1), capped to the enabled count.
Specified starting generals are included in the challenge count. Any additional
starting slots are random; non-starting enabled sets each get an unlock in the pool.

Keep the companion client running. Locked missions display the required unlock
item in-game, then exit to the menu after five seconds without sending DeathLink
or checks. A new generated room is required for these new unlocks and bonus checks.

## Permanent builder menu

New seeds use an in-game Archipelago button for permanent builder selections.
Enable `general_builder_unlocks` to add the nine general-specific builders to
USA Dozer, China Dozer and GLA Worker. The pool then needs twelve builder slots.
The menu permits one unlocked builder per faction, with an OFF toggle; reselect
your Command Center after changing it. Choices persist across missions and
DeathLink. Campaign and Generals Challenge Command Centers are supported.
The Abilities tab offers Reveal Minimap, Carpet Bomb, Patriot Airdrop and Emergency Repair.
Emergency Repair uses stock Level 3: an instant burst of up to 300 HP per eligible
friendly vehicle within radius 100, with a four-minute cooldown. The ability
cooldown multiplier applies. It requires no Command Center or Generals points.
Its unlock and cooldown persist across missions and DeathLink resets.
Generate a new seed with world 0.20.0 to include this new item. You can also choose
Emergency Repair under Starting Abilities. Older rooms remain compatible but
retain their original item pools.
Supply Drop and Reinforcements remain automatic. Builder swapping has player confirmation.



## Progressive Generals Powers (optional)

Enable **Progressive Generals Powers** in Permanent Unlocks in the YAML creator.
Each **Progressive Generals Point** item adds one point to your budget in every
mission, including Generals Challenges. Spend points separately for each mission.
Combat no longer awards Generals points; unit veterancy still works normally.

Rank depends on total received items, including points already spent:

| Total received points | General rank |
| --- | --- |
| 0-1 | 1 |
| 2 | 2 |
| 3 | 3 |
| 4-6 | 4 |
| 7+ | 5 |

Mission rank limits and hidden powers remain in effect. Free scripted powers
remain available. Save loads and DeathLink Quick Reset use that save's purchases
against your current received total, so later items are retained without granting
an extra budget on every load. A fresh mission starts with the full received budget.
Keep the client connected while playing.

The largest stock menu costs **18 points** (China and Infantry); 18 is the default
item count, with a range of **0-28**. The option is off by default. With all other
permanent unlocks enabled, the three story campaigns alone do not have enough
checks for 18 point items: increase checks per mission/set, add a challenge campaign, or reduce other item counts.

Install the included world, restart Archipelago, and generate a new room to enable
this option. Older compatible rooms keep their existing rules.
For testing, send `Progressive Generals Point`; verify mid-mission increases,
rank changes at 2/3/4/7 items (where permitted), purchases, a new mission and a
DeathLink reset. Progressive point delivery has both automated tests and player
confirmation in story and challenge missions.


## Configurable mission and set checks

In the YAML creator, **Check Counts** sets how many checks each victory awards:

- **Checks per mission:** 1-10, default **1**, for story and Generals Challenge missions.
- **Checks per completed set:** 0-10 additional checks, default **5**. Zero disables the set bonus.

For GLA 1-5, the total is `5 * checks per mission + checks per completed set`.
If GLA 4 is excluded, use four missions instead. Each mission/set awards its
checks once per room; replaying or changing difficulty does not repeat rewards.
The creator's totals, filler/trap preview and item-capacity validation update
with these settings.

All four trap weights now default to **50** (range 0-100). For example, 25 makes
one trap half as likely as a trap weighted 50; zero removes it. The overall trap
percentage is separate and defaults to 50% when traps are enabled.

Install the included world and generate a new room for these
options. Existing rooms retain their check counts and generated trap items.


## Useful item filler

After fixed items and traps, remaining slots use `mission_report_weight` (default 0), `supply_drop_weight` (50) and `reinforcements_weight` (50). Each ranges from 0 to 100. Zero excludes an item from weighted filler; at least one positive weight is required when such slots remain. Progressive Starting Cash remains a fixed 0-10 count (default 0), reserved before weighted slots. Supply Drop and Reinforcements use weights only; recreate YAMLs containing their old nonzero fixed counts. With traps enabled at 100%, no weighted filler slots remain. Use the creator preview to see chances and expected extra counts. Install world 0.19.0 and generate a new seed.

The in-game Progress tab is always enabled. It is no longer a YAML option.
The creator shows Sets required only for the set-count goal and Final mission
only for the final-mission goal, omitting irrelevant goal fields from YAML.
