"""Sims 3 mod storage and Mod The Sims adapter. Standard library only."""
from __future__ import annotations
import hashlib
import html
from html.parser import HTMLParser
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import tempfile
import threading
import uuid
import zipfile
from urllib.parse import urljoin, urlparse, parse_qs, unquote
from urllib.request import Request, build_opener, HTTPCookieProcessor, HTTPRedirectHandler
from http.cookiejar import CookieJar

LIMIT = 256 * 1024 * 1024
RESOURCE = 'Priority 500\n' + ''.join('PackedFile Packages/' + '*/' * n + '*.package\n' for n in range(5))


def safe_name(value):
    value = re.sub(r'[^\w. -]', '_', value).strip(' .')[:110]
    return value or 'mod'


def mts_url(url):
    p = urlparse(url)
    host = (p.hostname or '').lower()
    allowed = any(host == domain or host.endswith('.' + domain) for domain in ('modthesims.info', 'modthesims2.com'))
    if p.scheme != 'https' or not allowed or p.username or p.password or p.port not in (None, 443):
        raise ValueError('Bitte einen HTTPS-Link von modthesims.info verwenden.')
    return url


class MTSRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        mts_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class DownloadParser(HTMLParser):
    def __init__(self, base):
        super().__init__(convert_charrefs=True)
        self.base, self.files, self.title = base, {}, ''
        self.active = None
        self.in_title = False
        self.title_done = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'title' and not self.title_done:
            self.in_title = True
        if tag == 'a':
            href = urljoin(self.base, attrs.get('href', ''))
            p = urlparse(href)
            if p.path.endswith('/getfile.php') and parse_qs(p.query).get('file'):
                try:
                    mts_url(href)
                except ValueError:
                    return
                self.active = href
                self.files.setdefault(href, '')

    def handle_data(self, data):
        if self.in_title:
            self.title += data
        if self.active:
            self.files[self.active] += data

    def handle_endtag(self, tag):
        if tag == 'title' and self.in_title:
            self.in_title = False
            self.title_done = True
        if tag == 'a':
            self.active = None

    def results(self):
        return [{'url': u, 'name': n.strip() or ('Datei ' + parse_qs(urlparse(u).query)['file'][0])} for u, n in self.files.items()]


class MTSClient:
    def __init__(self):
        self.opener = build_opener(HTTPCookieProcessor(CookieJar()), MTSRedirect())

    def response(self, url, referer=None):
        mts_url(url)
        headers = {'User-Agent': 'Sims3ModManager/0.1 (desktop; user-requested downloads)'}
        if referer:
            headers['Referer'] = mts_url(referer)
        return self.opener.open(Request(url, headers=headers), timeout=40)

    def inspect(self, url):
        mts_url(url)
        p = urlparse(url)
        if not ((p.hostname or '') == 'modthesims.info' or (p.hostname or '').endswith('.modthesims.info')):
            raise ValueError('Bitte eine Mod-Seite auf modthesims.info verwenden.')
        if not (re.match(r'^/d/\d+', p.path) or (p.path == '/download.php' and parse_qs(p.query).get('t'))):
            raise ValueError('Eine Mod-Seite angeben: https://modthesims.info/d/123456/...')
        with self.response(url) as response:
            body = response.read(8 * 1024 * 1024 + 1)
            if len(body) > 8 * 1024 * 1024:
                raise ValueError('Mod-Seite ist zu groß.')
        parser = DownloadParser(url)
        parser.feed(body.decode('utf-8', errors='replace'))
        files = parser.results()
        if not files:
            raise ValueError('Keine Download-Dateien gefunden. Falls Login/Captcha erforderlich: Seite im Browser öffnen, herunterladen und Datei importieren.')
        return {'title': html.unescape(parser.title).replace('Mod The Sims - ', '').strip(), 'url': url, 'files': files}

    def download(self, url, folder, referer, progress=lambda value: None):
        folder = Path(folder)
        folder.mkdir(parents=True, exist_ok=True)
        temp = folder / (uuid.uuid4().hex + '.part')
        try:
            with self.response(url, referer) as response, temp.open('wb') as out:
                disposition = response.headers.get('Content-Disposition', '')
                match = re.search(r"filename\*=UTF-8''([^;]+)|filename=\"([^\"]+)\"|filename=([^;]+)", disposition, re.I)
                name = unquote(next((g for g in match.groups() if g), 'download')) if match else (Path(urlparse(response.geturl()).path).name if response.geturl() else 'download')
                name = safe_name(name)
                length = int(response.headers.get('Content-Length', '0'))
                if length > LIMIT:
                    raise ValueError('Download über 256 MiB wird nicht unterstützt.')
                size = 0
                while block := response.read(65536):
                    size += len(block)
                    if size > LIMIT:
                        raise ValueError('Download über 256 MiB wird nicht unterstützt.')
                    out.write(block)
                    progress(f'{size // 1024} KiB' + (f' / {length // 1024} KiB' if length else ''))
            with temp.open('rb') as handle:
                head = handle.read(256).lstrip().lower()
            if head.startswith((b'<!doctype html', b'<html')) or b'<html' in head:
                raise ValueError('Website lieferte eine Login-/Fehlerseite. Bitte im Browser herunterladen und importieren.')
            if not Path(name).suffix:
                name += '.zip' if zipfile.is_zipfile(temp) else '.package' if head.startswith(b'dbpf') else '.bin'
            destination = folder / (uuid.uuid4().hex[:8] + '-' + name)
            temp.replace(destination)
            return destination
        finally:
            temp.unlink(missing_ok=True)


def digest(path):
    with Path(path).open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def detect_game():
    home = Path.home()
    roots = [home / 'Documents', home / 'OneDrive' / 'Documents', home / 'OneDrive' / 'Dokumente']
    if os.name == 'nt':
        import ctypes
        buffer = ctypes.create_unicode_buffer(32768)
        if ctypes.windll.shell32.SHGetFolderPathW(None, 5, None, 0, buffer) == 0:
            roots.insert(0, Path(buffer.value))
    for root in roots:
        for name in ('The Sims 3', 'Die Sims 3'):
            candidate = root / 'Electronic Arts' / name
            if candidate.is_dir():
                return candidate
    return roots[0] / 'Electronic Arts' / 'The Sims 3'


class Library:
    def __init__(self, game):
        self.game = Path(game).expanduser().resolve()
        if not self.game.is_dir():
            raise ValueError('Bitte den vorhandenen Sims-3-Benutzerordner auswählen (mit Saves/Options.ini).')
        self.mods = self.game / 'Mods'
        self.root = self.mods / '.s3manager'
        self.root.mkdir(parents=True, exist_ok=True)
        self.db = self.root / 'library.json'
        self.lock = threading.RLock()
        self.records = json.loads(self.db.read_text('utf-8')) if self.db.exists() else []

    def save(self):
        temp = self.db.with_suffix('.tmp')
        temp.write_text(json.dumps(self.records, ensure_ascii=False, indent=2), 'utf-8')
        temp.replace(self.db)

    def target(self, record, enabled=None):
        state = record['enabled'] if enabled is None else enabled
        base = self.mods / 'Packages' / 'S3Manager' if state else self.root / 'disabled'
        return base / record['id']

    def framework(self):
        cfg = self.mods / 'Resource.cfg'
        if cfg.exists():
            content = cfg.read_text('utf-8-sig', errors='replace')
            # Add an explicit scope; preserve existing priority and override rules.
            rule = 'PackedFile Packages/S3Manager/*/*.package'
            if rule.lower() not in content.lower():
                backup = self.root / ('Resource-' + uuid.uuid4().hex[:8] + '.cfg.bak')
                shutil.copy2(cfg, backup)
                with cfg.open('a', encoding='utf-8') as handle:
                    handle.write('\nPriority 500\n' + rule + '\n')
        else:
            cfg.write_text(RESOURCE, 'utf-8')

    def install(self, source, title='', origin=''):
        source = Path(source)
        if source.stat().st_size > LIMIT:
            raise ValueError('Datei über 256 MiB wird nicht unterstützt.')
        with self.lock, tempfile.TemporaryDirectory(dir=self.root) as directory:
            staging = Path(directory)
            packages = []
            if source.suffix.lower() == '.package':
                packages = [(source.name, source.read_bytes())]
            elif zipfile.is_zipfile(source):
                with zipfile.ZipFile(source) as archive:
                    infos = archive.infolist()
                    if len(infos) > 5000 or sum(i.file_size for i in infos) > LIMIT:
                        raise ValueError('Archiv zu groß (maximal 256 MiB entpackt / 5000 Dateien).')
                    special = []
                    for item in infos:
                        path = PurePosixPath(item.filename.replace('\\', '/'))
                        if path.is_absolute() or '..' in path.parts or ':' in str(path):
                            raise ValueError('Unsicherer Pfad im Archiv.')
                        suffix = path.suffix.lower()
                        if suffix in ('.dll', '.asi', '.exe', '.sims3pack', '.sim', '.world'):
                            special.append(path.name)
                        if suffix == '.package' and not item.is_dir():
                            packages.append((path.name, archive.read(item)))
                    if special:
                        raise ValueError('Manuelle Installation erforderlich: ' + ', '.join(special[:5]) + '. Archiv bleibt erhalten; bitte Anleitung auf der Mod-Seite lesen.')
            else:
                raise ValueError('Unterstützt: .package und ZIP. RAR/7z zuerst mit 7-Zip entpacken und die .package-Dateien importieren.')
            if not packages:
                raise ValueError('Keine .package-Dateien gefunden.')
            filenames = set()
            hashes = set()
            for name, data in packages:
                name = safe_name(name)
                if name.lower() in filenames:
                    raise ValueError('Mehrere gleichnamige Packages im Archiv; Varianten bitte einzeln importieren.')
                if not data.startswith(b'DBPF'):
                    raise ValueError(f'{name}: keine gültige DBPF-Package-Datei.')
                filenames.add(name.lower())
                (staging / name).write_bytes(data)
                hashes.add(hashlib.sha256(data).hexdigest())
            existing = {f['sha256'] for record in self.records for f in record['files']}
            if hashes & existing:
                raise ValueError('Mindestens eine dieser Dateien ist bereits in der Bibliothek (SHA-256-Duplikat).')
            record = {'id': uuid.uuid4().hex, 'title': title or source.stem, 'source': origin, 'enabled': True,
                      'files': [{'name': p.name, 'sha256': digest(p)} for p in staging.iterdir()]}
            self.framework()
            target = self.target(record)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(staging, target)
            self.records.append(record)
            try:
                self.save()
            except Exception:
                self.records.remove(record)
                shutil.rmtree(target)
                raise
            return record

    def toggle(self, identifier):
        with self.lock:
            record = next(r for r in self.records if r['id'] == identifier)
            before, after = self.target(record), self.target(record, not record['enabled'])
            if not before.is_dir() or after.exists():
                raise ValueError('Mod-Dateien fehlen oder Ziel existiert bereits. Bitte Ordner prüfen.')
            for item in record['files']:
                path = before / item['name']
                if not path.is_file() or digest(path) != item['sha256']:
                    raise ValueError('Datei fehlt oder wurde extern verändert: ' + item['name'])
            after.parent.mkdir(parents=True, exist_ok=True)
            before.rename(after)
            record['enabled'] = not record['enabled']
            try:
                self.save()
            except Exception:
                record['enabled'] = not record['enabled']
                after.rename(before)
                raise

    def verify(self):
        issues = []
        for record in self.records:
            for item in record['files']:
                path = self.target(record) / item['name']
                if not path.is_file() or digest(path) != item['sha256']:
                    issues.append(record['title'] + ': ' + item['name'])
        return issues
