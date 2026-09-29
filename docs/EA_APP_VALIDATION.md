# EA App executable validation

Checked on 2026-09-29 with client 0.8.2. This record applies to the inspected
English EA App installation, not every EA App release or modified installation.

## Result

The installed Zero Hour `game.dat` is compatible with the current adapter's
on-disk checks. No address overrides or client code changes were required.

- EA executable size: 6,551,960 bytes.
- EA SHA-256: `253feba0a5503cb4d49fd07463b17d3cc84731e583f9625cb90fcd8b5cac0221`.
- All 327 native address anchors resolve successfully.
- Every mapped PE section is byte-for-byte identical to the historical supported
  Steam baseline (`420fba1dbdc4c14e2418c2b0d3010b9fac6f314eafa1f3a101805b8d98883ea1`).
  The compared sections are `.text`, `.rdata`, `.data`, `.data1` and `.rsrc`.
- All 327 resolved addresses differ from the currently installed updated Steam
  executable (`f37a4929f8d697104e99c2bcf46f8d833122c943afcd87fd077df641d344495b`).
  The resolver already maps these addresses for each executable; fixed addresses
  must not be copied between those two builds.
- `INIZH.big`, `PatchINI.big`, `PatchZH.big` and `MapsZH.big` are byte-for-byte
  identical between the inspected EA App and Steam installations.

## Validation performed

The complete Archipelago pytest suite was run with both installed-game variables
pointing at the EA App installation: **1,236 passed, 1 skipped**.

The executable-backed compatibility test checked native function prefixes,
callback tables, menu functions, save/load, mission control, item effects,
reinforcements, selling, progressive points and airdrop table relationships.
Generated callback bytes were checked without installing or executing them.

The skipped test requires a historical Steam `Game.dat.bak` in the selected
installation. Its absence in the EA folder is not a compatibility failure.
Separately, seven exact parachute/cargo instruction fixtures were verified against
the EA executable, and the full mapped image was compared with the available
historical Steam baseline in the Steam installation.

## Live testing limit

The user reported initial in-game tests working. This session could enumerate
`Generals.exe` and `game.dat`, but Windows denied module/memory access to both
running processes. Their executable paths and live instruction bytes could not
be independently verified. No running game memory or installed files were changed.

This confirms the inspected executable and asset compatibility. It does not
certify injected DLLs, every campaign/ability or every future EA App update.
