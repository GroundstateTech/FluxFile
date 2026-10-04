import json
from pathlib import Path
import tempfile
import unittest
from fluxfile_session import load_session, SESSION_SCHEMA


class SessionValidationTests(unittest.TestCase):
    def check_invalid(self, payload):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'session.json'
            path.write_text(json.dumps(payload))
            with self.assertRaises(ValueError):
                load_session(path)

    def test_non_object_payload(self):
        for payload in ([], None, 'queue'):
            with self.subTest(payload=payload):
                self.check_invalid(payload)

    def test_invalid_metrics(self):
        for value in (float('nan'), float('inf'), -1, 'invalid'):
            with self.subTest(value=value):
                self.check_invalid({'schema': SESSION_SCHEMA, 'version': 1,
                                    'jobs': [{'source': '/missing/example.txt', 'duration_seconds': value}]})

    def test_duplicate_ids(self):
        self.check_invalid({'schema': SESSION_SCHEMA, 'version': 1,
                            'jobs': [{'id': 'same', 'source': '/missing/one.txt'},
                                     {'id': 'same', 'source': '/missing/two.txt'}]})

    def test_invalid_versions(self):
        for version in (None, [], {}, True, 1.5, float('inf'), 'invalid'):
            with self.subTest(version=version):
                self.check_invalid({'schema': SESSION_SCHEMA, 'version': version, 'jobs': []})

    def test_non_string_layout_falls_back_to_flat(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'session.json'
            for layout in ([], {}, None):
                path.write_text(json.dumps({'schema': SESSION_SCHEMA, 'version': 2,
                                            'jobs': [], 'settings': {'layout': layout}}))
                _, settings = load_session(path)
                self.assertEqual(settings['layout'], 'flat')
