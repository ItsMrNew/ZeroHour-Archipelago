import sys


def main():
    if len(sys.argv) > 1:
        # Keep existing direct command-line invocations working. The GUI binary
        # has no console; its companion opens one for interactive diagnostics.
        if getattr(sys, 'frozen', False):
            import subprocess
            from pathlib import Path
            return subprocess.call([str(Path(sys.executable).parent / 'Diagnostics' / 'ZeroHourClientConsole.exe'),
                                    *sys.argv[1:]], creationflags=subprocess.CREATE_NEW_CONSOLE)
        from zh.client import main as console_main
        return console_main()
    from zh.client_ui import main as gui_main
    return gui_main()

if __name__ == "__main__":
    raise SystemExit(main())
