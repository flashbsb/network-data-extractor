#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test Suite: Root Portal Admin & Operations Visibility
=====================================================
Verifies that the "Admin & Operations" navigation card:
1. Points to '/admin/index.html'.
2. Is hidden by default in files/static mode (#card-admin display: none).
3. Automatically reveals itself when accessed via DB mode (db_available / active_mode: 'db').
"""

import os
import tempfile
import unittest
from pathlib import Path
from core.root_portal_engine import generate_root_portal
from core.theme_system import THEME_SCRIPT_JS


class TestRootPortalAdminVisibility(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.TemporaryDirectory()
        self.outbase = self.test_dir.name

    def tearDown(self):
        self.test_dir.cleanup()

    def test_root_portal_admin_card_structure(self):
        generate_root_portal(self.outbase)
        index_file = Path(self.outbase) / "index.html"
        self.assertTrue(index_file.exists(), "index.html was not generated")

        content = index_file.read_text(encoding="utf-8")

        # 1. Check CSS hides #card-admin by default
        self.assertIn("#card-admin { display: none; }", content)

        # 2. Check card element has id, href to /admin/index.html, and inline style display: none
        self.assertIn('id="card-admin"', content)
        self.assertIn('href="/admin/index.html"', content)
        self.assertIn('style="display: none;"', content)
        self.assertIn("Admin & Operations", content)

        # 3. Check capabilities detection script is present and toggles card-admin
        self.assertIn("detectStorageCapabilities", content)
        self.assertIn("var adminCard = document.getElementById('card-admin');", content)
        self.assertIn("adminCard.style.display = 'flex';", content)
        self.assertIn("adminCard.style.display = 'none';", content)

    def test_theme_system_script_admin_toggle(self):
        self.assertIn("var adminCard = document.getElementById('card-admin');", THEME_SCRIPT_JS)
        self.assertIn("adminCard.style.display = 'flex';", THEME_SCRIPT_JS)
        self.assertIn("adminCard.style.display = 'none';", THEME_SCRIPT_JS)


if __name__ == "__main__":
    unittest.main()
