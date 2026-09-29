# Zero Hour Archipelago — Install and Play

**Client 0.8.4 · Archipelago 0.6.7 · Windows · Steam / EA App**

Play Command & Conquer: Generals – Zero Hour campaigns and Generals Challenges
as part of an Archipelago multiworld. Mission victories send checks to the room;
received items unlock mission sets, builders, abilities and other benefits.
You can play alone or alongside players of other Archipelago games.

## What you need

- An installed copy of **stock English Zero Hour on Steam or the EA App**.
- [Archipelago for Windows](https://github.com/ArchipelagoMW/Archipelago/releases).
  This release is tested with **Archipelago 0.6.7**. Include the generator during
  installation if you will create the world for your group.
- The **ZeroHour-Archipelago-0.8.4-Launcher.zip** package from
  [Zero Hour Archipelago Releases](https://github.com/ItsMrNew/ZeroHour-Archipelago/releases).

**Both the Steam and EA App versions have been tested and verified as working.**
Steam with GenPatcher 2.14 fixes and GenTool 8.9 has also been tested successfully.
Generals Online is **not compatible**. GenLauncher and The First Decade
are untested. This integration is for single-player campaigns and Generals
Challenges; it does not connect Zero Hour online matches.

## 1. Install Zero Hour Client

1. Download **ZeroHour-Archipelago-0.8.4-Launcher.zip** and extract it into a folder.
2. Open **Archipelago Launcher** and choose **Install APWorld**.
3. Select **generals_zh.apworld** from the extracted package.
4. Close and reopen Archipelago Launcher. **Zero Hour Client** will now appear in
   its client list; use the search box if needed.

The APWorld includes the Zero Hour client and its runtime dependencies. Opening
**Zero Hour Client** extracts it automatically. A separate Python installation or
client EXE download is not required. Keep the other package files for configuring
your world and installing optional saves.

Install just one Zero Hour APWorld. The separate **0.8.4 Windows** distribution is
an alternative for people who prefer opening `ZeroHourClient.exe` directly; its
APWorld does not add a client entry to Archipelago Launcher. Both distributions
use the same game client. The instructions below use the Launcher distribution.

## 2. Create your player YAML with Zero Hour Options.html

A **YAML** is a settings file for one player slot. It tells Archipelago which game
you are playing and which options to use when generating the world.

**We recommend the included Zero Hour Options.html instead of Archipelago
Launcher's Generate Template Options.** Our creator explains the Zero Hour
settings, shows the expected check count as you change them, and checks whether
your selected items fit the available checks.

1. Open **Zero Hour Options.html** from the extracted package in your web browser.
   It runs locally; you do not need to upload the HTML file anywhere.
2. Enter your **Player / slot name**. The default is `ZeroHour`. Use a unique name for
   each slot in a multiworld and remember it for connecting later.
3. Select your campaigns, Generals Challenges, starting mission sets and victory
   goal. Choose checks per mission/set, unlocks, helpful items, traps and DeathLink
   as desired. Read the descriptions beside each option.
4. Review the live check totals, item-pool summary and any validation messages.
   Resolve errors before downloading. If **Disable Unit Only Missions** is enabled,
   read the [optional saves section](#6-optional-mission-start-saves).
5. Click **Download YAML**. Your browser saves **ZeroHour.yaml**; check Downloads.

The included example YAML is optional. Use your downloaded file for your chosen
settings. Changing the HTML settings or YAML after generation does not change an
existing room; generate a new world to use different generation settings.

For a group, send your YAML to the person generating the multiworld. Each separate
player slot needs its own YAML. Only that person needs to perform steps 3 and 4.
If your room is already hosted, continue to [connect and play](#5-connect-and-play).

## 3. Generate your world locally

Zero Hour is a **custom APWorld**, so generate on a computer with its APWorld
installed. You can then use archipelago.gg to host the result.

1. Find your Archipelago installation folder, commonly
   `C:\ProgramData\Archipelago`, and open **Players**.
2. Place your downloaded YAML directly in **Players**. For a multiworld, put all
   participants' YAMLs there, with unique player names and filenames. Move unused
   YAMLs elsewhere so they do not create extra slots. Do not include both your
   downloaded YAML and the example for the same player.
3. The person generating must install the required APWorlds for every custom game
   in the group. Other games may also require their own generation assets; follow
   those games' setup guides.
4. In Archipelago Launcher, open **Generate** and wait for successful completion.
   If it reports an error, fix the named option or missing game requirement and retry.
5. Open Archipelago's **output** folder. Find the newly generated `AP_<seed>.zip`.
   The generator log gives the exact path if your folders are configured differently.

Keep this generated ZIP for hosting. Your **YAML** contains choices;
**generals_zh.apworld** installs the integration; `AP_<seed>.zip` contains the
world generated for this particular game session.

## 4. Upload the generated world and create a room

1. Open [Archipelago — Host Game](https://archipelago.gg/uploads).
2. Click **Upload File** and select the generated `AP_<seed>.zip` from **output**.
   Keep it zipped. The release ZIP, YAML and `.apworld` are not the generated world.
3. On the seed page, choose **Create Room** and wait for the room to start.
4. Save the room-page link and share it with the players. Use the displayed
   **server address and port**, such as `archipelago.gg:12345`, when connecting.

If you return to an inactive room, reopen that room page to resume it and use the
address it displays. Reuse the same room to continue your progress.

These steps follow Archipelago's [official setup and hosting guide](https://archipelago.gg/tutorial/Archipelago/setup_en).

## 5. Connect and play

1. In Archipelago Launcher, open **Zero Hour Client**.
2. Fill in the connection fields:

   | Field | What to enter |
   | --- | --- |
   | Server (host:port) | The address shown on your room page, including its port |
   | Player slot | Your YAML player name, exactly as listed in the room |
   | Room password | Leave blank unless your host set a join password |

3. Click **Connect** and check the log for a successful connection and inventory
   synchronization. `archipelago.gg:5000` is only the initial placeholder; replace
   it with your room's address.
4. Start **Zero Hour through Steam or the EA App**. If it is already running, the
   client can attach to it. Check the log for game detection. If prompted to restart
   the game after ability assets are installed, do so before using those abilities.
5. Start an unlocked campaign or Generals Challenge, or load a mission-start save.
   **Keep Zero Hour Client connected while loading, playing and finishing missions.**

Use the **Archipelago** button in the game for:

- **Progress:** completed, remaining and in-logic checks. Available at the main menu.
- **DeathLink:** follow your YAML or change the live DeathLink behaviour.
- **Notifications:** choose your items, all players' transfers or off, and duration.
- **Builders and Abilities:** use received permanent unlocks during missions.

DeathLink and Notifications are also available at the main menu. Locked mission
sets show the unlock item needed and return you to the menu. Completing a mission
awards its configured checks once per room; replaying it does not grant extra checks.
Normal game saves preserve your battlefield progress; Archipelago tracks your
received items and completed checks separately.

## 6. Optional mission-start saves

**Optional-Mission-Start-Saves.zip** helps you start a particular mission without
first playing the preceding missions. Use your own suitable mission-start saves
if you already have them. Otherwise, the pack may be needed to reach later missions
directly with your chosen settings.

For example, **Disable Unit Only Missions** removes **USA 3 and GLA 4** from
Archipelago checks and set-completion requirements. It does not change the game's
normal campaign sequence or automatically skip those missions. To avoid playing
them just to reach the next mission, load the supplied **USA 4** or **GLA 5**
mission-start save. The corresponding campaign must still be unlocked.

### Install the saves

1. Close Zero Hour and Zero Hour Client, then extract
   **Optional-Mission-Start-Saves.zip**.
2. Open your Windows **Documents** folder, then
   **Command and Conquer Generals Zero Hour Data\Save**. Create **Save** if it is
   missing. Documents may be redirected to OneDrive; use the folder where your
   game stores its saves, rather than the game installation directory.
3. In the extracted save pack, open **Easy\Save**, **Medium\Save** or **Hard\Save**.
   Copy the `.sav` files you want directly into the game's **Save** folder. You may
   install multiple difficulties. Do not copy the difficulty folders into **Save**.
   Preserve any existing files with matching names instead of overwriting them.
4. Start the client, connect, start Zero Hour, then choose **LOAD**. Select an entry
   such as **Archipelago - Easy - USA 4** or **Archipelago - Hard - GLA 5**.

The pack has **240 starts**: 15 story missions and 65 challenge battles at three
difficulties. They start the stock mission and its scripted opening, rather than
loading a pre-built army or a completed mission. They do not give Archipelago
items, bypass mission locks, or award checks for missions you skip. Starting a later
mission does not complete earlier checks that are still enabled in your YAML.

These are mission starts, not DeathLink Quick Reset checkpoints. Keep the client
connected through loading so it can apply your unlocks and starting effects.
The pack was built and tested against stock Steam mission data; see its
**README.txt** for save-format and rank-baseline details.

## Saved preferences and local progress

The client remembers connection fields and your Light/Dark theme when it closes.
A field left blank returns to its default on the next launch.

- **Launcher client files:** `%LOCALAPPDATA%\ZeroHourArchipelagoLauncher\clients\<bundle-hash>`
- **Launcher preferences and local progress:** `%LOCALAPPDATA%\ZeroHourArchipelagoLauncher\UserData\ZeroHourArchipelago`
- **Standalone Windows preferences and local progress:** `%LOCALAPPDATA%\ZeroHourArchipelago`

You can paste these folder paths into File Explorer, omitting the `<bundle-hash>`
placeholder when browsing the client cache. Game saves live in Documents as above.

## Troubleshooting

| Problem | What to check |
| --- | --- |
| Zero Hour Client is missing in Archipelago Launcher | Install the Launcher package's APWorld and restart Archipelago Launcher. |
| Generation says Zero Hour is unknown | Install its APWorld on the computer running Generate, then restart Archipelago. |
| The creator reports too many items for the checks | Increase checks or enabled mission sets, or reduce fixed unlock/item counts. |
| Cannot connect to the room | Open the room page; check its current host/port, exact slot name and password. |
| Access denied to the game process | If Zero Hour is elevated, close the client and reopen Archipelago Launcher as administrator before opening Zero Hour Client. |
| A mission returns to the main menu | Read the required mission-set unlock in the client log or in-game notice. |
| Optional saves are absent from LOAD | Put the `.sav` files directly in the active Documents game-data **Save** folder. |

For compatibility details, see the [compatibility guide](https://github.com/ItsMrNew/ZeroHour-Archipelago/blob/main/docs/COMPATIBILITY.md).
Report issues with the client version, storefront, mission and relevant log messages
on [GitHub Issues](https://github.com/ItsMrNew/ZeroHour-Archipelago/issues).

## Source and licenses

The [source repository](https://github.com/ItsMrNew/ZeroHour-Archipelago) includes
[development/build instructions](https://github.com/ItsMrNew/ZeroHour-Archipelago/blob/main/docs/DEVELOPMENT.md).
Dependency licenses and **THIRD_PARTY_NOTICES.md** are included with the release.
The package does not include the game itself.

Unofficial community integration; not an EA, Valve or Archipelago release.
