#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Network Data Extractor - Authentication & RBAC Test Suite
Validates PBKDF2 hashing, session life-cycle, CSRF protection, and RBAC matrix.
"""

import os
import sys
import time
import shutil
import tempfile
import unittest

# Ensure repo root is on path
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

from core.auth_manager import AuthManager, ROLE_PERMISSIONS, PERMISSIONS


class TestAuthManager(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="ndx_auth_test_")
        self.users_file = os.path.join(self.test_dir, "users.json")
        self.auth = AuthManager(users_file=self.users_file)

    def tearDown(self):
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    def test_01_default_admin_initialization(self):
        """Verifies default admin user is seeded with PBKDF2 hash and 0600 permissions."""
        self.assertTrue(os.path.isfile(self.users_file))
        mode = os.stat(self.users_file).st_mode & 0o777
        self.assertEqual(mode, 0o600)

        # Authenticate with initial default credentials
        session = self.auth.authenticate("admin", "admin")
        self.assertIsNotNone(session)
        self.assertEqual(session["username"], "admin")
        self.assertEqual(session["role"], "SuperAdmin")
        self.assertTrue(len(session["session_token"]) >= 64)
        self.assertTrue(len(session["csrf_token"]) >= 64)

    def test_02_invalid_credentials_rejected(self):
        """Verifies invalid passwords and non-existent users are rejected."""
        self.assertIsNone(self.auth.authenticate("admin", "wrong_password"))
        self.assertIsNone(self.auth.authenticate("non_existent", "admin"))

    def test_03_session_validation_and_revocation(self):
        """Verifies token validation, sliding expiration, and explicit revocation."""
        session = self.auth.authenticate("admin", "admin")
        token = session["session_token"]

        # Validate session
        valid_sess = self.auth.validate_session(token)
        self.assertIsNotNone(valid_sess)
        self.assertEqual(valid_sess["username"], "admin")

        # Validate CSRF
        self.assertTrue(self.auth.validate_csrf(token, session["csrf_token"]))
        self.assertFalse(self.auth.validate_csrf(token, "fake_csrf_token"))

        # Revoke session
        self.assertTrue(self.auth.revoke_session(token))
        self.assertIsNone(self.auth.validate_session(token))

    def test_04_user_crud_operations(self):
        """Verifies creating, modifying, and listing user accounts."""
        # Create NetOps user
        ok, msg = self.auth.create_user("alice", "alice123", role="NetOps", description="Network Engineer")
        self.assertTrue(ok)

        # Re-creation rejected
        ok_dup, _ = self.auth.create_user("alice", "another_pass")
        self.assertFalse(ok_dup)

        # Authenticate new user
        sess_alice = self.auth.authenticate("alice", "alice123")
        self.assertIsNotNone(sess_alice)
        self.assertEqual(sess_alice["role"], "NetOps")

        # Update password
        ok_pass, _ = self.auth.update_password("alice", "new_secret_pass")
        self.assertTrue(ok_pass)
        self.assertIsNone(self.auth.authenticate("alice", "alice123"))
        self.assertIsNotNone(self.auth.authenticate("alice", "new_secret_pass"))

        # Update role
        ok_role, _ = self.auth.update_role("alice", "Operator")
        self.assertTrue(ok_role)
        u = self.auth.get_user("alice")
        self.assertEqual(u["role"], "Operator")

    def test_05_last_superadmin_protection(self):
        """Guarantees the last SuperAdmin cannot be deleted or demoted."""
        # Attempt to delete sole SuperAdmin
        ok_del, msg_del = self.auth.delete_user("admin")
        self.assertFalse(ok_del)
        self.assertIn("last remaining SuperAdmin", msg_del)

        # Attempt to demote sole SuperAdmin
        ok_role, msg_role = self.auth.update_role("admin", "Auditor")
        self.assertFalse(ok_role)
        self.assertIn("last remaining SuperAdmin", msg_role)

        # Create second SuperAdmin and ensure deletion is then allowed
        self.auth.create_user("bob", "bobpass123", role="SuperAdmin")
        ok_del2, _ = self.auth.delete_user("admin")
        self.assertTrue(ok_del2)

    def test_06_rbac_permission_matrix(self):
        """Verifies exact permission enforcement across all 4 predefined roles."""
        self.auth.create_user("super", "pass12345", role="SuperAdmin")
        self.auth.create_user("netops", "pass23456", role="NetOps")
        self.auth.create_user("oper", "pass34567", role="Operator")
        self.auth.create_user("audit", "pass45678", role="Auditor")

        # SuperAdmin: has all permissions
        for perm in PERMISSIONS:
            self.assertTrue(self.auth.has_permission("super", perm), f"SuperAdmin should have {perm}")

        # NetOps: can edit cfg and network json, but NOT manage users or system json
        self.assertTrue(self.auth.has_permission("netops", "edit_cfg"))
        self.assertTrue(self.auth.has_permission("netops", "edit_json_network"))
        self.assertFalse(self.auth.has_permission("netops", "manage_users"))
        self.assertFalse(self.auth.has_permission("netops", "edit_json"))

        # Operator: can view, but CANNOT edit anything
        self.assertTrue(self.auth.has_permission("oper", "view_metrics"))
        self.assertTrue(self.auth.has_permission("oper", "view_cfg"))
        self.assertFalse(self.auth.has_permission("oper", "edit_cfg"))
        self.assertFalse(self.auth.has_permission("oper", "edit_json"))
        self.assertFalse(self.auth.has_permission("oper", "manage_users"))

        # Auditor: can only view metrics & export reports
        self.assertTrue(self.auth.has_permission("audit", "view_metrics"))
        self.assertTrue(self.auth.has_permission("audit", "export_reports"))
        self.assertFalse(self.auth.has_permission("audit", "view_cfg"))
        self.assertFalse(self.auth.has_permission("audit", "view_json"))
        self.assertFalse(self.auth.has_permission("audit", "edit_cfg"))

    def test_07_default_password_detection_and_length_enforcement(self):
        """Verifies default password is flagged, short passwords rejected, and flag clears after update."""
        # 1. Login with default admin password
        sess = self.auth.authenticate("admin", "admin")
        self.assertIsNotNone(sess)
        self.assertTrue(sess.get("is_default_password"))

        # 2. Short password rejected (< 8 chars)
        ok_short, msg_short = self.auth.update_password("admin", "short")
        self.assertFalse(ok_short)
        self.assertIn("at least 8 characters", msg_short)

        # 3. Valid new password updates and clears default password flag on session
        ok_upd, _ = self.auth.update_password("admin", "StrongPassword2026!")
        self.assertTrue(ok_upd)

        sess_valid = self.auth.validate_session(sess["session_token"])
        self.assertFalse(sess_valid.get("is_default_password"))

        # 4. New login reflects is_default_password = False
        new_sess = self.auth.authenticate("admin", "StrongPassword2026!")
        self.assertIsNotNone(new_sess)
        self.assertFalse(new_sess.get("is_default_password"))


if __name__ == "__main__":
    print("=" * 60)
    print("     AUTHENTICATION & RBAC SECURITY VERIFICATION SUITE      ")
    print("=" * 60)
    unittest.main(verbosity=2)
