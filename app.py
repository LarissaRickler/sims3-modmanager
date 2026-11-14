"""German desktop interface. Run with Python 3.11+ on Windows."""
import json
import os
from pathlib import Path
import queue
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import webbrowser
from core import Library, MTSClient, detect_game

BASE = Path(__file__).resolve().parent
CONFIG = BASE / 'settings.json'


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('Sims 3 · Mod Manager')
        self.geometry('1050x700')
        self.minsize(850, 580)
        self.configure(bg='#101827')
        self.events = queue.Queue()
        self.client = MTSClient()
        self.library = None
        self.page = None
        self.busy = False
        self.buttons = []
        self.path = tk.StringVar(value=str(detect_game()))
        if CONFIG.exists():
            try:
                self.path.set(json.loads(CONFIG.read_text('utf-8'))['game'])
            except (ValueError, KeyError, OSError):
                pass
        self.url = tk.StringVar()
        self.status = tk.StringVar(value='Bereit · Spiel vor Änderungen schließen.')
        style = ttk.Style(self)
        style.theme_use('clam')
        style.configure('TFrame', background='#101827')
        style.configure('TLabel', background='#101827', foreground='#e4eaf5', font=('Segoe UI', 10))
        style.configure('Title.TLabel', font=('Segoe UI', 25, 'bold'))
        style.configure('TButton', font=('Segoe UI', 10), padding=8)
        style.configure('Treeview', rowheight=32, font=('Segoe UI', 10))
        outer = ttk.Frame(self, padding=24)
        outer.pack(fill='both', expand=True)
        ttk.Label(outer, text='SIMS 3 / MOD MANAGER', style='Title.TLabel').pack(anchor='w')
        ttk.Label(outer, text='Mod The Sims herunterladen · Packages verwalten · Dateien prüfen').pack(anchor='w', pady=(2, 18))
        row = ttk.Frame(outer)
        row.pack(fill='x')
        ttk.Label(row, text='Sims-3-Benutzerordner:').pack(side='left')
        ttk.Entry(row, textvariable=self.path).pack(side='left', fill='x', expand=True, padx=8)
        self.button(row, 'Ordner wählen', self.choose_folder).pack(side='left')
        self.button(row, 'Verbinden', self.connect).pack(side='left', padx=(8, 0))
        notebook = ttk.Notebook(outer)
        notebook.pack(fill='both', expand=True, pady=18)
        downloads = ttk.Frame(notebook, padding=16)
        library = ttk.Frame(notebook, padding=16)
        notebook.add(downloads, text='  Mod The Sims  ')
        notebook.add(library, text='  Meine Mods  ')
        ttk.Label(downloads, text='Mod-Link einfügen (https://modthesims.info/d/…):').pack(anchor='w')
        urlrow = ttk.Frame(downloads)
        urlrow.pack(fill='x', pady=8)
        ttk.Entry(urlrow, textvariable=self.url).pack(side='left', fill='x', expand=True)
        self.button(urlrow, 'Dateien laden', self.inspect).pack(side='left', padx=(8, 0))
        self.button(urlrow, 'Im Browser', self.browser).pack(side='left', padx=(8, 0))
        self.heading = ttk.Label(downloads, text='Wähle eine Datei passend zu deiner Spielversion und zur Mod-Anleitung.')
        self.heading.pack(anchor='w', pady=8)
        self.files = ttk.Treeview(downloads, columns=('file',), show='headings', selectmode='browse', height=7)
        self.files.heading('file', text='Verfügbare Dateien / Varianten')
        self.files.pack(fill='both', expand=True)
        bar = ttk.Frame(downloads)
        bar.pack(fill='x', pady=12)
        self.button(bar, 'Herunterladen & installieren', self.download).pack(side='left')
        self.button(bar, 'MTS durchsuchen ↗', lambda: webbrowser.open('https://modthesims.info/downloads/ts3/')).pack(side='left', padx=8)
        ttk.Label(downloads, text='Login/Captcha? Im Browser herunterladen und unter „Meine Mods“ importieren.\nAutomatische Installation: .package und ZIP. Spezialmods benötigen ihre eigene Anleitung.').pack(anchor='w')
        self.mods = ttk.Treeview(library, columns=('name', 'state', 'count'), show='headings', selectmode='browse')
        for col, label, width in [('name', 'Mod', 450), ('state', 'Status', 120), ('count', 'Packages', 90)]:
            self.mods.heading(col, text=label)
            self.mods.column(col, width=width)
        self.mods.pack(fill='both', expand=True)
        actions = ttk.Frame(library)
        actions.pack(fill='x', pady=12)
        self.button(actions, 'Dateien importieren', self.import_files).pack(side='left')
        self.button(actions, 'Aktivieren / Deaktivieren', self.toggle).pack(side='left', padx=8)
        self.button(actions, 'Dateien prüfen', self.verify).pack(side='left')
        self.button(actions, 'Quellseite ↗', self.source).pack(side='left', padx=8)
        ttk.Label(library, text='Nur von dieser App verwaltete Mods werden angezeigt. Deaktivierte Mods bleiben gespeichert.\nDie Dateiprüfung erkennt Änderungen; sie prüft keine spielinternen Mod-Konflikte.').pack(anchor='w')
        self.progress = ttk.Progressbar(outer, mode='indeterminate')
        self.progress.pack(fill='x')
        ttk.Label(outer, textvariable=self.status, wraplength=960).pack(anchor='w', pady=(8, 0))
        self.after(100, self.poll)
        self.protocol('WM_DELETE_WINDOW', self.close)
        if Path(self.path.get()).is_dir():
            self.connect()

    def button(self, parent, text, command):
        button = ttk.Button(parent, text=text, command=command)
        self.buttons.append(button)
        return button

    def close(self):
        if self.busy:
            messagebox.showinfo('Vorgang läuft', 'Bitte den laufenden Vorgang abwarten.', parent=self)
            return
        self.destroy()

    def run(self, work, done):
        if self.busy:
            return
        self.busy = True
        for button in self.buttons:
            button.state(['disabled'])
        self.progress.start()
        self.status.set('Vorgang läuft …')
        def worker():
            try:
                value = work()
                self.events.put(('done', done, value))
            except Exception as exc:
                self.events.put(('error', str(exc)))
        threading.Thread(target=worker, daemon=True).start()

    def poll(self):
        try:
            while True:
                event = self.events.get_nowait()
                if event[0] == 'progress':
                    self.status.set('Download: ' + event[1])
                    continue
                self.busy = False
                for button in self.buttons:
                    button.state(['!disabled'])
                self.progress.stop()
                if event[0] == 'error':
                    self.status.set(event[1])
                    messagebox.showerror('Vorgang fehlgeschlagen', event[1], parent=self)
                else:
                    try:
                        event[1](event[2])
                    except Exception as exc:
                        messagebox.showerror('Fehler', str(exc), parent=self)
        except queue.Empty:
            pass
        self.after(100, self.poll)

    def choose_folder(self):
        path = filedialog.askdirectory(title='Sims-3-Benutzerordner auswählen (enthält Saves/Options.ini)')
        if path:
            self.path.set(path)
            self.connect()

    def connect(self):
        try:
            candidate = Path(self.path.get())
            if not ((candidate / 'Options.ini').exists() or (candidate / 'Saves').is_dir()):
                raise ValueError('Dieser Ordner enthält weder Saves noch Options.ini. Bitte den Sims-3-Benutzerordner auswählen; Spiel dafür einmal starten.')
            self.library = Library(candidate)
            self.path.set(str(self.library.game))
            CONFIG.write_text(json.dumps({'game': str(self.library.game)}, ensure_ascii=False), 'utf-8')
            self.refresh()
            self.status.set('Verbunden · ' + str(self.library.game))
        except Exception as exc:
            self.library = None
            self.mods.delete(*self.mods.get_children())
            messagebox.showerror('Ordner prüfen', str(exc), parent=self)

    def require_library(self):
        if not self.library:
            messagebox.showinfo('Benutzerordner fehlt', 'Zuerst den Sims-3-Benutzerordner verbinden.', parent=self)
            return False
        return True

    def refresh(self):
        self.mods.delete(*self.mods.get_children())
        for mod in self.library.records:
            self.mods.insert('', 'end', iid=mod['id'], values=(mod['title'], 'Aktiv' if mod['enabled'] else 'Deaktiviert', len(mod['files'])))

    def inspect(self):
        url = self.url.get().strip()
        def done(page):
            self.page = page
            self.heading.configure(text=page['title'])
            self.files.delete(*self.files.get_children())
            for i, item in enumerate(page['files']):
                self.files.insert('', 'end', iid=str(i), values=(item['name'],))
            self.status.set(f'{len(page["files"])} Datei(en) gefunden. Gewünschte Variante auswählen.')
        self.run(lambda: self.client.inspect(url), done)

    def browser(self):
        from core import mts_url
        try:
            webbrowser.open(mts_url(self.url.get().strip()))
        except ValueError as exc:
            messagebox.showerror('Link prüfen', str(exc), parent=self)

    def download(self):
        if not self.require_library():
            return
        selection = self.files.selection()
        if not selection or not self.page:
            messagebox.showinfo('Datei wählen', 'Mod-Seite laden und eine Download-Datei auswählen.', parent=self)
            return
        item = self.page['files'][int(selection[0])]
        page, lib = self.page, self.library
        def work():
            file = self.client.download(item['url'], lib.root / 'downloads', page['url'], lambda v: self.events.put(('progress', v)))
            try:
                return lib.install(file, page['title'], page['url'])
            except Exception as exc:
                raise ValueError(str(exc) + '\nDownload gespeichert: ' + str(file)) from exc
        self.run(work, self.installed)

    def installed(self, record):
        self.refresh()
        self.status.set('Installiert: ' + record['title'])

    def import_files(self):
        if not self.require_library():
            return
        files = filedialog.askopenfilenames(title='Packages oder ZIP-Dateien importieren', filetypes=[('Sims-3-Mods', '*.package *.zip'), ('Alle Dateien', '*.*')])
        if not files:
            return
        lib = self.library
        def work():
            successes, errors = 0, []
            for file in files:
                try:
                    lib.install(file)
                    successes += 1
                except Exception as exc:
                    errors.append(Path(file).name + ': ' + str(exc))
            return successes, errors
        def done(result):
            self.refresh()
            self.status.set(f'{result[0]} Mod(s) importiert.')
            if result[1]:
                messagebox.showwarning('Import-Ergebnis', '\n'.join(result[1]), parent=self)
        self.run(work, done)

    def toggle(self):
        if self.require_library() and self.mods.selection():
            identifier = self.mods.selection()[0]
            lib = self.library
            self.run(lambda: lib.toggle(identifier), lambda _: (self.refresh(), self.status.set('Mod-Status geändert.')))

    def verify(self):
        if self.require_library():
            self.run(self.library.verify, lambda issues: messagebox.showinfo('Dateiprüfung', '\n'.join(issues) if issues else 'Alle verwalteten Dateien sind unverändert vorhanden.', parent=self))

    def source(self):
        if self.library and self.mods.selection():
            record = next(r for r in self.library.records if r['id'] == self.mods.selection()[0])
            if record['source']:
                webbrowser.open(record['source'])


if __name__ == '__main__':
    App().mainloop()
