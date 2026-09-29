"""Owned desktop window for the AP client, independent of Windows Terminal."""
import asyncio
import ctypes
import logging
import os
from pathlib import Path
import queue
import sys
import threading
import tkinter as tk
from tkinter import ttk
from tkinter.scrolledtext import ScrolledText

from .client import ZeroHourClient, server_url
from .window_icon import WindowIcon, enable_display_scaling
from .launcher_settings import load_settings, save_settings
from .version import VERSION

THEMES = {
    'light': {'bg':'#f2f4f7', 'fg':'#182431', 'field':'#ffffff', 'muted':'#596675',
              'button':'#e0e6ed', 'active':'#cbd8e6', 'border':'#a9b6c5', 'select':'#2467a6'},
    'dark': {'bg':'#18212b', 'fg':'#edf2f7', 'field':'#101820', 'muted':'#acb8c6',
             'button':'#2e4053', 'active':'#3c5570', 'border':'#536a81', 'select':'#326b9e'},
}
# Same four item colours, darkened on a light background for readable contrast.
LIGHT_ITEM_COLOURS = {'#AF99EF':'#7651B0', '#6D8BE8':'#3055B2',
                     '#FA8072':'#B43F32', '#00EEEE':'#007E83'}


class ClientSession:
    """Run/cancel the existing client without accessing Tk from its worker."""

    def __init__(self, factory=ZeroHourClient):
        self.factory = factory
        self.thread = None
        self.loop = self.task = None
        self.stopping = threading.Event()
        self.client = None

    @property
    def running(self):
        return self.thread is not None and self.thread.is_alive()

    def start(self, server, slot, password, state_dir):
        if self.running:
            raise RuntimeError('The previous connection is still stopping.')
        self.stopping.clear()
        self.client = None
        self.thread = threading.Thread(target=self._run, args=(server, slot, password, state_dir))
        self.thread.start()

    def _run(self, *args):
        async def run():
            self.loop = asyncio.get_running_loop()
            self.task = asyncio.current_task()
            if self.stopping.is_set():
                return
            self.client = self.factory(*args)
            logging.getLogger('ZeroHour').info('Keep this client open while playing.')
            await self.client.run()
        try:
            asyncio.run(run())
        except asyncio.CancelledError:
            pass
        except Exception as error:
            logging.getLogger('ZeroHour').error('%s', error)
        finally:
            self.loop = self.task = None
            logging.getLogger('ZeroHour').info('Client stopped. Recorded checks are saved.')

    def stop(self):
        if self.stopping.is_set():
            return  # Do not cancel again while native hook cleanup is running.
        self.stopping.set()
        loop, task = self.loop, self.task
        if loop is not None and task is not None:
            try:
                loop.call_soon_threadsafe(task.cancel)
            except RuntimeError:
                pass  # Worker already finished and closed its event loop.


class LogQueue(logging.Handler):
    def __init__(self):
        super().__init__()
        self.messages = queue.Queue(maxsize=2000)
        self.setFormatter(logging.Formatter('%(asctime)s %(message)s', datefmt='%H:%M:%S'))

    def emit(self, record):
        try:
            colour = getattr(record, 'log_colour', None)
            if (record.name == 'ZeroHour' and record.levelno >= logging.WARNING
                    and 'Access denied to game process' in record.getMessage()):
                colour = '#FA8072'
            self.messages.put_nowait((self.format(record), getattr(record, 'item_parts', None),
                                     colour))
        except queue.Full:
            pass


def icon_path():
    # Embedded copy also works if only the EXE is moved to the desktop.
    root = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[1]))
    return root / 'assets' / 'zero_hour_archipelago.ico'


class ClientWindow:
    def __init__(self, root, session=None, preferences_path=None):
        self.root = root
        self.preferences_path = preferences_path
        preferences = load_settings(preferences_path)
        self.session = session or ClientSession()
        self.closing = False
        self.handler = LogQueue()
        logging.getLogger().addHandler(self.handler)
        logging.getLogger().setLevel(logging.INFO)
        root.title(f'Zero Hour Archipelago {VERSION} - Steam / EA App')
        root.geometry('850x540')
        root.minsize(640, 400)
        root.iconbitmap(default=str(icon_path()))
        self.window_icon = WindowIcon(root, icon_path()) if os.name == 'nt' else None
        root.protocol('WM_DELETE_WINDOW', self.close)
        frame = ttk.Frame(root, padding=12)
        frame.pack(fill='both', expand=True)
        frame.columnconfigure(1, weight=1)
        frame.rowconfigure(5, weight=1)
        self.server = tk.StringVar(value=preferences['server'])
        self.slot = tk.StringVar(value=preferences['slot'])
        self.password = tk.StringVar(value=preferences['password'])
        self.theme = tk.StringVar(value=preferences['theme'].title())
        self.status = tk.StringVar(value='Enter your room address and player slot, then connect.')
        self.entries = []
        for row, (label, variable) in enumerate((('Server (host:port)', self.server),
                                                ('Player slot', self.slot),
                                                ('Room password (optional)', self.password))):
            ttk.Label(frame, text=label).grid(row=row, column=0, sticky='w', padx=(0, 12), pady=4)
            entry = ttk.Entry(frame, textvariable=variable, show='*' if row == 2 else '')
            entry.grid(row=row, column=1, sticky='ew', pady=4)
            self.entries.append(entry)
        self.button = ttk.Button(frame, text='Connect', command=self.toggle)
        self.button.grid(row=3, column=1, sticky='e', pady=8)
        appearance = ttk.Frame(frame)
        appearance.grid(row=3, column=0, sticky='w', pady=8)
        ttk.Label(appearance, text='Theme').pack(side='left', padx=(0,8))
        self.theme_picker = ttk.Combobox(appearance, textvariable=self.theme,
                                        values=('Light','Dark'), state='readonly', width=7)
        self.theme_picker.pack(side='left')
        self.theme_picker.bind('<<ComboboxSelected>>', self.change_theme)
        ttk.Label(frame, textvariable=self.status).grid(row=4, column=0, columnspan=2, sticky='w', pady=(0, 8))
        self.log = ScrolledText(frame, wrap='word', state='disabled', font=('Consolas', 10))
        self.log.grid(row=5, column=0, columnspan=2, sticky='nsew')
        self.style = ttk.Style(root)
        self.style.theme_use('clam')  # Native Windows theme ignores dark field colours.
        self.apply_theme()
        root.bind('<Return>', lambda event: self.toggle())
        self.entries[0].focus_set()
        self.poll_id = root.after(100, self.poll)

    def remember(self):
        try:
            save_settings({'server':self.server.get(), 'slot':self.slot.get(),
                           'password':self.password.get(), 'theme':self.theme.get().lower()}, self.preferences_path)
        except (OSError, ValueError, AttributeError):
            logging.getLogger('ZeroHour').warning('Could not save launcher preferences.')

    def change_theme(self, event=None):
        self.apply_theme()
        self.remember()

    def apply_theme(self):
        c = THEMES[self.theme.get().lower()]
        self.root.configure(background=c['bg'])
        self.style.configure('.', background=c['bg'], foreground=c['fg'],
                             bordercolor=c['border'], lightcolor=c['border'], darkcolor=c['border'])
        for name in ('TEntry','TCombobox'):
            self.style.configure(name, fieldbackground=c['field'], foreground=c['fg'],
                                 insertcolor=c['fg'], arrowcolor=c['fg'], background=c['button'])
            self.style.map(name, fieldbackground=[('disabled',c['bg']),('readonly',c['field'])],
                           foreground=[('disabled',c['muted']),('readonly',c['fg'])],
                           selectbackground=[('!disabled',c['select'])],
                           selectforeground=[('!disabled','#ffffff')])
        self.style.configure('TButton', background=c['button'], padding=(10,5))
        self.style.map('TButton', background=[('active',c['active'])],
                       foreground=[('disabled',c['muted'])])
        self.root.option_add('*TCombobox*Listbox.background',c['field'])
        self.root.option_add('*TCombobox*Listbox.foreground',c['fg'])
        self.root.option_add('*TCombobox*Listbox.selectBackground',c['select'])
        self.root.option_add('*TCombobox*Listbox.selectForeground','#ffffff')
        self.log.configure(background=c['field'], foreground=c['fg'], insertbackground=c['fg'],
                           selectbackground=c['select'], selectforeground='#ffffff',
                           highlightbackground=c['border'], highlightcolor=c['border'], relief='flat',
                           padx=8, pady=8)
        self.log.vbar.configure(background=c['button'], activebackground=c['active'],
                                troughcolor=c['bg'])
        for colour, light_colour in LIGHT_ITEM_COLOURS.items():
            self.log.tag_configure(colour, foreground=light_colour if self.theme.get() == 'Light' else colour)

    def toggle(self):
        if self.closing or self.session.stopping.is_set() and self.session.running:
            return
        if self.session.running:
            self.session.stop()
        else:
            try:
                server = server_url(self.server.get())
            except ValueError as error:
                self.status.set(str(error))
                return
            state_dir = Path(os.environ.get('LOCALAPPDATA', '.')) / 'ZeroHourArchipelago' / 'progress'
            self.remember()
            self.session.start(server, self.slot.get().strip() or 'ZeroHour', self.password.get() or None, state_dir)
            for entry in self.entries:
                entry.configure(state='disabled')
            self.button.configure(text='Disconnect')
            self.status.set('Connecting...')

    def poll(self):
        lines = []
        for _ in range(200):
            try:
                lines.append(self.handler.messages.get_nowait())
            except queue.Empty:
                break
        if lines:
            at_bottom = self.log.yview()[1] >= .99
            self.log.configure(state='normal')
            for message, parts, colour in lines:
                if colour:
                    self.log.insert('end', message + '\n', (colour,))
                elif parts:
                    body = ''.join(text for text, _ in parts)
                    prefix = message[:-len(body)] if body and message.endswith(body) else ''
                    self.log.insert('end', prefix, ())
                    for text, colour in parts:
                        self.log.insert('end', text, (colour,) if colour else ())
                    self.log.insert('end', '\n', ())
                else:
                    self.log.insert('end', message + '\n', ())
            excess = int(self.log.index('end-1c').split('.')[0]) - 3000
            if excess > 0:
                self.log.delete('1.0', f'{excess + 1}.0')
            self.log.configure(state='disabled')
            if at_bottom:
                self.log.see('end')
        if self.session.running:
            stopping = self.session.stopping.is_set()
            self.button.configure(state='disabled' if stopping else 'normal')
            self.status.set('Stopping safely...' if stopping else
                            'Connected — keep this window open while playing.' if self.session.client and self.session.client.connected else
                            'Connecting / reconnecting — see the log below.')
        elif self.closing:
            logging.getLogger().removeHandler(self.handler)
            self.handler.close()
            self.root.destroy()
            return
        elif self.session.thread is not None:
            self.status.set('Disconnected. Recorded checks are saved.')
            self.button.configure(text='Connect', state='normal')
            for entry in self.entries:
                entry.configure(state='normal')
        self.poll_id = self.root.after(100, self.poll)

    def close(self):
        if not self.closing:
            self.remember()
        self.closing = True
        self.button.configure(state='disabled')
        self.session.stop()


def main():
    enable_display_scaling()
    if os.name == 'nt':
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('ZeroHour.Archipelago.Client')
    root = tk.Tk()
    ClientWindow(root)
    root.mainloop()
    return 0
