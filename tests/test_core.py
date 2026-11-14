import json
from pathlib import Path
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch
from urllib.request import build_opener
import zipfile
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core import Library, DownloadParser, MTSClient, mts_url

PACKAGE = b'DBPF' + b'\0' * 92


class LibraryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.game = self.root / 'The Sims 3'
        self.game.mkdir()
        self.lib = Library(self.game)

    def archive(self, entries):
        path = self.root / 'mod.zip'
        with zipfile.ZipFile(path, 'w') as archive:
            for name, data in entries.items():
                archive.writestr(name, data)
        return path

    def test_install_disable_reopen_enable(self):
        record = self.lib.install(self.archive({'folder/a.package': PACKAGE, 'readme.txt': b'hello'}), 'Test')
        self.assertTrue((self.lib.target(record) / 'a.package').exists())
        self.assertIn('Packages/', (self.lib.mods / 'Resource.cfg').read_text())
        self.lib.toggle(record['id'])
        self.assertFalse(record['enabled'])
        reopened = Library(self.game)
        self.assertEqual(reopened.verify(), [])
        reopened.toggle(record['id'])
        self.assertTrue(reopened.records[0]['enabled'])

    def test_framework_preserves_existing(self):
        cfg = self.lib.mods / 'Resource.cfg'
        cfg.write_text('Priority 999\nPackedFile Overrides/*.package\n')
        self.lib.install(self.archive({'a.package': PACKAGE}))
        self.assertTrue(cfg.read_text().startswith('Priority 999'))
        self.assertEqual(len(list(self.lib.root.glob('*.cfg.bak'))), 1)
        self.lib.framework()
        self.assertEqual(len(list(self.lib.root.glob('*.cfg.bak'))), 1)

    def test_duplicate_rejected(self):
        archive = self.archive({'a.package': PACKAGE})
        self.lib.install(archive)
        with self.assertRaisesRegex(ValueError, 'bereits'):
            self.lib.install(archive)
        self.assertEqual(len(self.lib.records), 1)

    def test_traversal_and_executables_rejected(self):
        for entries in [{'../outside.package': PACKAGE}, {'C:/a.package': PACKAGE}, {'a.package': PACKAGE, 'patch.dll': b'x'}]:
            with self.subTest(entries=entries):
                with self.assertRaises(ValueError):
                    self.lib.install(self.archive(entries))
        self.assertEqual(self.lib.records, [])
        self.assertFalse((self.root / 'outside.package').exists())

    def test_same_basename_variants_rejected(self):
        with self.assertRaisesRegex(ValueError, 'gleichnamige'):
            self.lib.install(self.archive({'a/variant.package': PACKAGE, 'b/variant.package': PACKAGE + b'2'}))

    def test_corrupt_package_rejected(self):
        with self.assertRaisesRegex(ValueError, 'DBPF'):
            self.lib.install(self.archive({'a.package': b'<html>error'}))

    def test_integrity_protects_modified_files(self):
        record = self.lib.install(self.archive({'a.package': PACKAGE}))
        (self.lib.target(record) / 'a.package').write_bytes(b'changed')
        self.assertEqual(len(self.lib.verify()), 1)
        with self.assertRaisesRegex(ValueError, 'verändert'):
            self.lib.toggle(record['id'])
        self.assertTrue(record['enabled'])

    def test_db_failure_rolls_back_install(self):
        with patch.object(self.lib, 'save', side_effect=OSError('disk full')):
            with self.assertRaises(OSError):
                self.lib.install(self.archive({'a.package': PACKAGE}))
        self.assertEqual(self.lib.records, [])
        self.assertEqual(list((self.lib.mods / 'Packages' / 'S3Manager').iterdir()), [])

    def test_db_failure_rolls_back_toggle(self):
        record = self.lib.install(self.archive({'a.package': PACKAGE}))
        with patch.object(self.lib, 'save', side_effect=OSError('disk full')):
            with self.assertRaises(OSError):
                self.lib.toggle(record['id'])
        self.assertTrue(record['enabled'])
        self.assertTrue(self.lib.target(record).is_dir())


class AdapterTests(unittest.TestCase):
    def test_parser_relative_mirror_duplicate(self):
        parser = DownloadParser('https://modthesims.info/d/1234/example')
        parser.feed('<title>Mod The Sims - Demo</title><a href="//chii.modthesims.info/getfile.php?file=12">Demo.zip</a><a href="https://chii.modthesims.info/getfile.php?file=12">Download</a><a href="https://evil.example/getfile.php?file=1">bad</a>')
        self.assertEqual(len(parser.results()), 1)
        self.assertIn('Demo.zip', parser.results()[0]['name'])
        parser.feed('<svg><title>Unrelated icon</title></svg>')
        self.assertEqual(parser.title, 'Mod The Sims - Demo')
        self.assertEqual(mts_url('https://skuld.modthesims2.com/files/example.zip'), 'https://skuld.modthesims2.com/files/example.zip')

    def test_hosts_rejected(self):
        for url in ['http://modthesims.info/d/1', 'https://modthesims.info.evil.test/d/1', 'https://evil.test/d/1', 'https://user@modthesims.info/d/1', 'https://modthesims.info:999/d/1']:
            with self.assertRaises(ValueError):
                mts_url(url)

    def test_download_with_local_http_server(self):
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                body = b'<html>Login</html>' if self.path == '/html' else PACKAGE
                self.send_response(200)
                self.send_header('Content-Disposition', 'attachment; filename="test.package"')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            def log_message(self, *args):
                pass
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            client = MTSClient()
            # Production hostname validation remains strict; substitute transport only.
            client.response = lambda url, referer=None: build_opener().open(f'http://127.0.0.1:{server.server_port}{url}')
            with tempfile.TemporaryDirectory() as folder:
                result = client.download('/file', folder, 'unused')
                self.assertEqual(result.read_bytes(), PACKAGE)
                with self.assertRaisesRegex(ValueError, 'Login'):
                    client.download('/html', folder, 'unused')
                self.assertEqual(list(Path(folder).glob('*.part')), [])
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


if __name__ == '__main__':
    unittest.main()
