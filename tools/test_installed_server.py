"""Integration test with an installed AP server and a disposable generated seed.

Pass the server EXE and .archipelago file. Synthetic victory inputs are used;
this tests AP compatibility, not the actual game's victory signal.
"""
import argparse
import asyncio
import logging
from pathlib import Path
import socket
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from zh.client import ZeroHourClient
from zh.mission_data import LOCATION_IDS, DOZER_ITEM_ID, BUILDER_ITEMS, CASH_ITEM_ID, POWER_TRAP_ID


async def check(server_exe, seed, slot="ZeroHourPlayer", expected_items=15, expect_dozer=False, starting_dozer=False, starting_builders=False, starting_effects=False):
    with socket.socket() as port_socket:
        port_socket.bind(("127.0.0.1", 0))
        port = port_socket.getsockname()[1]
    with tempfile.TemporaryDirectory(prefix="zero-hour-ap-test-") as directory:
        directory = Path(directory)
        log = directory / "server.log"
        with log.open("w", encoding="utf-8") as output:
            process = subprocess.Popen([
                str(server_exe), str(seed), "--host", "127.0.0.1", "--port", str(port),
                "--disable_save", "--password", "", "--auto_shutdown", "30",
            ], stdout=output, stderr=subprocess.STDOUT, stdin=subprocess.PIPE,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            client = ZeroHourClient(f"127.0.0.1:{port}", slot, state_dir=directory / "progress")
            task = asyncio.create_task(client.network())
            try:
                async def wait_for(predicate):
                    while not predicate():
                        if task.done():
                            task.result()
                            raise AssertionError("Client ended before completing the test")
                        if process.poll() is not None:
                            raise AssertionError("Server exited: " + log.read_text(encoding="utf-8", errors="replace"))
                        await asyncio.sleep(0.1)
                await asyncio.wait_for(wait_for(lambda: client.connected), 30)
                if starting_builders:
                    await asyncio.wait_for(wait_for(lambda: client.inventory_confirmed and all(client.inventory.count(item) >= 1 for item in BUILDER_ITEMS)), 10)
                    assert client.builder_mode and not client.acknowledged
                    print("PASS: All three builders received before any mission checks.")
                if starting_dozer:
                    await asyncio.wait_for(wait_for(lambda: client.inventory_confirmed and client.inventory.count(DOZER_ITEM_ID) >= 1), 10)
                    assert not client.acknowledged
                    print("PASS: Starting USA Dozer received before any mission checks.")
                if starting_effects:
                    await asyncio.wait_for(wait_for(lambda: client.inventory_confirmed and client.inventory.count(CASH_ITEM_ID) == 1 and client.inventory.count(POWER_TRAP_ID) == 1), 10)
                    assert client.effects_mode and not client.acknowledged
                    print("PASS: Starting cash and power trap received before any mission checks.")
                # Mission-set rooms must receive each unlock before later
                # victories can be submitted. Replay only synthetic inputs
                # while the actual server delivers the progression items.
                for _ in range(100):
                    locations = (m['id'] for m in client.selected_missions) if client.sets_mode else client.location_ids
                    for location in locations:
                        client.victory(location)
                    if client.acknowledged == client.location_ids:
                        break
                    await asyncio.sleep(0.1)
                await asyncio.wait_for(wait_for(lambda: client.acknowledged == client.location_ids), 10)
                await asyncio.wait_for(wait_for(lambda: client.inventory.synchronized and len(client.inventory.items) == expected_items), 10)
                if expect_dozer or starting_dozer:
                    assert (client.dozer_mode or client.builder_mode) and client.inventory.count(DOZER_ITEM_ID) >= 1
                    assert any(item.item == DOZER_ITEM_ID for item in client.progress.received)
                if starting_effects:
                    assert client.inventory.count(CASH_ITEM_ID) == 3
                    assert client.inventory.count(POWER_TRAP_ID) == 3
                    # AP starting inventory uses flags=0; location rewards carry classification.
                    traps = [item for item in client.inventory.items if item.item == POWER_TRAP_ID and item.location > 0]
                    cash = [item for item in client.inventory.items if item.item == CASH_ITEM_ID and item.location > 0]
                    assert len(traps) == len(cash) == 2
                    assert all(item.flags == 4 for item in traps), traps
                    assert all(item.flags == 2 for item in cash), cash
                    print("PASS: Three cash items and three traps have correct AP classifications.")
                await asyncio.sleep(0.5)
                print(f"PASS: AP server authenticated and acknowledged all {len(client.location_ids)} synthetic mission checks.")
                print(f"PASS: Client received and saved all {expected_items} items from the actual AP server.")
            finally:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
                if process.poll() is None:
                    try:
                        process.communicate(b"/exit\n", timeout=10)
                    except subprocess.TimeoutExpired:
                        process.terminate()
                        process.wait(timeout=5)
        server_log = log.read_text(encoding="utf-8", errors="replace")
        if "has completed their goal" not in server_log:
            print(server_log[-5000:])
            raise AssertionError("Server did not record goal completion")
        print("PASS: AP server recorded CLIENT_GOAL after acknowledgement.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("server", type=Path)
    parser.add_argument("seed", type=Path)
    parser.add_argument("--slot", default="ZeroHourPlayer")
    parser.add_argument("--expected-items", type=int, default=15)
    parser.add_argument("--expect-dozer", action="store_true")
    parser.add_argument("--starting-dozer", action="store_true")
    parser.add_argument("--starting-builders", action="store_true")
    parser.add_argument("--starting-effects", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    asyncio.run(check(args.server.resolve(), args.seed.resolve(), args.slot, args.expected_items, args.expect_dozer, args.starting_dozer, args.starting_builders, args.starting_effects))
