import asyncio
import logging
import threading
import time
import tkinter as tk

from zh.client_ui import ClientSession, ClientWindow, icon_path


def wait_until(predicate):
    end = time.monotonic() + 5
    while not predicate() and time.monotonic() < end:
        time.sleep(.01)
    assert predicate()


def test_session_disconnect_waits_for_cleanup_and_reconnects(tmp_path):
    started, cleaned = threading.Event(), threading.Event()
    arguments = []

    class Client:
        def __init__(self, *args):
            arguments.append(args)

        async def run(self):
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                await asyncio.sleep(.05)
                cleaned.set()

    session = ClientSession(Client)
    for _ in range(2):
        started.clear()
        cleaned.clear()
        session.start('ws://localhost:1234', 'ZeroHour', None, tmp_path)
        assert started.wait(5)
        session.stop()
        session.stop()
        wait_until(lambda: not session.running)
        assert cleaned.is_set()
    assert arguments == [('ws://localhost:1234', 'ZeroHour', None, tmp_path)] * 2


def test_close_immediately_after_start(tmp_path):
    session = ClientSession(lambda *args: None)
    session.stopping.set()
    # Exercise the shutdown-before-worker-ready branch deterministically.
    session._run('ws://localhost', 'ZeroHour', None, tmp_path)
    assert session.client is None
    assert session.loop is None


def test_window_icon_validation_logs_and_graceful_close(tmp_path):
    started, cleaned = threading.Event(), threading.Event()

    class Client:
        connected = True

        def __init__(self, *args):
            self.args = args

        async def run(self):
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                cleaned.set()

    root = tk.Tk()
    root.withdraw()
    session = ClientSession(Client)
    window = ClientWindow(root, session, tmp_path/'launcher.json')
    try:
        assert icon_path().is_file()
        assert window.slot.get() == 'ZeroHour'
        assert window.server.get() == 'archipelago.gg:5000'
        assert window.entries[2].cget('show') == '*'
        window.server.set('')
        window.toggle()
        assert 'required' in window.status.get()
        assert not session.running
        window.server.set('localhost:1234')
        window.toggle()
        assert started.wait(5)
        logging.getLogger('ZeroHour').info('Test item received')
        root.after_cancel(window.poll_id)
        window.poll()
        assert 'Connected' in window.status.get()
        assert 'Test item received' in window.log.get('1.0', 'end')
        assert session.client.args[:3] == ('ws://localhost:1234', 'ZeroHour', None)
        window.close()
        wait_until(lambda: not session.running)
        assert cleaned.is_set()
        root.after_cancel(window.poll_id)
        window.poll()
        assert window.handler not in logging.getLogger().handlers
    finally:
        session.stop()
        if session.thread:
            session.thread.join(5)
        try:
            root.destroy()
        except tk.TclError:
            pass
        logging.getLogger().removeHandler(window.handler)


def test_launcher_preferences_theme_close_reopen_and_blank_reset(tmp_path):
    from zh.client_ui import THEMES
    from zh.launcher_settings import load_settings, DEFAULTS
    path = tmp_path/'launcher.json'
    root = tk.Tk(); root.withdraw()
    window = ClientWindow(root, preferences_path=path)
    try:
        assert window.server.get() == DEFAULTS['server']
        assert window.theme.get() == 'Light'
        window.server.set('archipelago.gg:54321')
        window.slot.set('My Player')
        window.password.set('test-room-password')
        window.theme.set('Dark'); window.change_theme()
        assert window.log.cget('background') == THEMES['dark']['field']
        assert window.log.cget('foreground') == THEMES['dark']['fg']
        assert window.style.lookup('TEntry','fieldbackground') == THEMES['dark']['field']
        assert load_settings(path)['theme'] == 'dark'
        # Saving happens on close even without connecting or changing theme.
        window.slot.set('My Updated Player')
        window.close(); root.after_cancel(window.poll_id); window.poll()
        assert 'test-room-password' not in path.read_text()
        root = tk.Tk(); root.withdraw()
        window = ClientWindow(root, preferences_path=path)
        assert window.server.get() == 'archipelago.gg:54321'
        assert window.slot.get() == 'My Updated Player'
        assert window.password.get() == 'test-room-password'
        assert window.theme.get() == 'Dark'
        window.server.set('  '); window.slot.set(''); window.password.set('')
        window.theme.set('Light'); window.change_theme()
        assert window.log.cget('background') == THEMES['light']['field']
        window.close(); root.after_cancel(window.poll_id); window.poll()
        assert load_settings(path) == DEFAULTS
    finally:
        logging.getLogger().removeHandler(window.handler)
        try: root.destroy()
        except tk.TclError: pass


def test_invalid_preferences_and_password_do_not_prevent_launch(tmp_path):
    from zh.launcher_settings import load_settings, DEFAULTS
    path = tmp_path/'launcher.json'
    for content in ('{broken', '[]', '{"server":null,"slot":false,"theme":"pink"}',
                    '{"password_protected":"not base64"}', '{"password":"plaintext"}'):
        path.write_text(content)
        assert load_settings(path) == DEFAULTS


def test_log_colours_only_item_names_and_rethemes_existing_text(tmp_path):
    from zh.client_ui import LIGHT_ITEM_COLOURS
    root = tk.Tk(); root.withdraw()
    window = ClientWindow(root, preferences_path=tmp_path/'launcher.json')
    try:
        for colour, name in (('#AF99EF','Unlock'),('#6D8BE8','Helpful'),
                             ('#00EEEE','Filler'),('#FA8072','Trap')):
            parts = [('Sender sent ',None),(name,colour),(' to Receiver',None)]
            logging.getLogger('ZeroHour').info('%s',''.join(t for t,_ in parts), extra={'item_parts':parts})
        parts = [('Received: ',None),('Supply Drop','#00EEEE')]
        logging.getLogger('ZeroHour').info('Received: Supply Drop',extra={'item_parts':parts})
        logging.getLogger('ZeroHour').info('Normal status')
        root.after_cancel(window.poll_id); window.poll()
        assert 'Sender sent Filler to Receiver' in window.log.get('1.0','end')
        for colour in LIGHT_ITEM_COLOURS:
            assert window.log.tag_ranges(colour)
            assert window.log.tag_cget(colour,'foreground') == LIGHT_ITEM_COLOURS[colour]
        for needle in ('Sender','Receiver','Received:','Normal status'):
            assert not window.log.tag_names(window.log.search(needle,'1.0'))
        window.theme.set('Dark'); window.change_theme()
        for colour in LIGHT_ITEM_COLOURS:
            assert window.log.tag_cget(colour,'foreground') == colour
        window.close(); root.after_cancel(window.poll_id); window.poll()
    finally:
        logging.getLogger().removeHandler(window.handler)
        try: root.destroy()
        except tk.TclError: pass
