#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Network Data Extractor - Authentication & RBAC Security Engine
Provides zero-dependency cryptographic password hashing (PBKDF2-HMAC-SHA256),
session management with sliding TTL, CSRF token validation, and Role-Based Access Control.
"""

import os
import json
import time
import secrets
import hashlib
from pathlib import Path
from typing import Dict, Any, Optional, List, Set, Tuple


# ------------------------------------------------------------------------------
# RBAC ROLE & PERMISSION DEFINITIONS
# ------------------------------------------------------------------------------

PERMISSIONS = {
    "manage_users": "Create, edit, and delete user accounts and assign roles",
    "edit_json": "Edit system and engine JSON configurations",
    "edit_json_network": "Edit network and topology JSON configurations",
    "edit_cfg": "Edit network device elements.cfg and commands.cfg files",
    "view_json": "Read JSON configurations",
    "view_cfg": "Read network elements and commands configuration files",
    "view_metrics": "View execution summaries, run history, and system metrics",
    "export_reports": "Download inventory, diff, and topology report datasets",
}

ROLE_PERMISSIONS: Dict[str, Set[str]] = {
    "SuperAdmin": {
        "manage_users",
        "edit_json",
        "edit_json_network",
        "edit_cfg",
        "view_json",
        "view_cfg",
        "view_metrics",
        "export_reports",
    },
    "NetOps": {
        "edit_json_network",
        "edit_cfg",
        "view_json",
        "view_cfg",
        "view_metrics",
        "export_reports",
    },
    "Operator": {
        "view_json",
        "view_cfg",
        "view_metrics",
        "export_reports",
    },
    "Auditor": {
        "view_metrics",
        "export_reports",
    },
}


# ------------------------------------------------------------------------------
# AUTHENTICATION MANAGER CLASS
# ------------------------------------------------------------------------------

class AuthManager:
    """
    Manages local user credentials with PBKDF2 hashing, secure session tokens,
    CSRF token protection, and granular role-based authorization.
    """

    PBKDF2_ITERATIONS = 100_000
    SESSION_TTL_SECONDS = 4 * 3600  # 4 hours default

    def __init__(self, users_file: Optional[str] = None):
        """
        Initializes the authentication engine.
        :param users_file: Custom path to users JSON file. Falls back to config/users.json
                           or environment variable NDX_USERS_FILE.
        """
        if users_file:
            self.users_file = os.path.abspath(users_file)
        elif os.environ.get("NDX_USERS_FILE"):
            self.users_file = os.path.abspath(os.environ["NDX_USERS_FILE"])
        else:
            base_dir = Path(__file__).resolve().parent.parent
            self.users_file = os.path.join(base_dir, "config", "users.json")

        self.sessions: Dict[str, Dict[str, Any]] = {}
        self._ensure_users_file()

    def _ensure_users_file(self) -> None:
        """Ensures the users file exists with secure permissions and default admin."""
        os.makedirs(os.path.dirname(self.users_file), exist_ok=True)
        if not os.path.isfile(self.users_file):
            # Seed with default admin account
            salt = secrets.token_hex(16)
            initial_pass = "admin"
            pass_hash = self._hash_password(initial_pass, salt)
            
            default_data = {
                "users": {
                    "admin": {
                        "username": "admin",
                        "role": "SuperAdmin",
                        "password_hash": pass_hash,
                        "salt": salt,
                        "created_at": int(time.time()),
                        "updated_at": int(time.time()),
                        "description": "Built-in System Administrator"
                    }
                }
            }
            self._save_users_data(default_data)
            try:
                # Restrict file permissions to owner read/write (0600)
                os.chmod(self.users_file, 0o600)
            except Exception:
                pass

    def _load_users_data(self) -> Dict[str, Any]:
        """Loads and returns the users dictionary from file."""
        if not os.path.isfile(self.users_file):
            return {"users": {}}
        try:
            with open(self.users_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {"users": {}}

    def _save_users_data(self, data: Dict[str, Any]) -> None:
        """Atomically saves the users dictionary to disk."""
        tmp_file = f"{self.users_file}.tmp.{secrets.token_hex(4)}"
        with open(tmp_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp_file, self.users_file)
        try:
            os.chmod(self.users_file, 0o600)
        except Exception:
            pass

    @classmethod
    def _hash_password(cls, password: str, salt_hex: str) -> str:
        """Computes PBKDF2-HMAC-SHA256 hash using the provided salt."""
        salt = bytes.fromhex(salt_hex)
        derived = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt,
            cls.PBKDF2_ITERATIONS
        )
        return derived.hex()

    # --------------------------------------------------------------------------
    # USER MANAGEMENT METHODS
    # --------------------------------------------------------------------------

    def list_users(self) -> List[Dict[str, Any]]:
        """Returns safe user profiles (excluding password hashes and salts)."""
        data = self._load_users_data()
        user_list = []
        for u in data.get("users", {}).values():
            user_list.append({
                "username": u.get("username"),
                "role": u.get("role", "Operator"),
                "created_at": u.get("created_at"),
                "updated_at": u.get("updated_at"),
                "description": u.get("description", "")
            })
        return user_list

    def get_user(self, username: str) -> Optional[Dict[str, Any]]:
        """Returns a single user profile without secret hash."""
        data = self._load_users_data()
        u = data.get("users", {}).get(username)
        if not u:
            return None
        return {
            "username": u.get("username"),
            "role": u.get("role", "Operator"),
            "created_at": u.get("created_at"),
            "updated_at": u.get("updated_at"),
            "description": u.get("description", "")
        }

    def create_user(self, username: str, password: str, role: str = "Operator", description: str = "") -> Tuple[bool, str]:
        """Creates a new user account with hashed password and role."""
        username = username.strip()
        if not username or len(username) < 3:
            return False, "Username must be at least 3 characters long"
        if not password or len(password) < 4:
            return False, "Password must be at least 4 characters long"
        if role not in ROLE_PERMISSIONS:
            return False, f"Invalid role '{role}'. Allowed roles: {', '.join(ROLE_PERMISSIONS.keys())}"

        data = self._load_users_data()
        if username in data.get("users", {}):
            return False, f"User '{username}' already exists"

        salt = secrets.token_hex(16)
        pass_hash = self._hash_password(password, salt)
        now = int(time.time())

        data.setdefault("users", {})[username] = {
            "username": username,
            "role": role,
            "password_hash": pass_hash,
            "salt": salt,
            "created_at": now,
            "updated_at": now,
            "description": description
        }
        self._save_users_data(data)
        return True, "User created successfully"

    def update_password(self, username: str, new_password: str) -> Tuple[bool, str]:
        """Updates the password for an existing user."""
        if not new_password or len(new_password) < 4:
            return False, "Password must be at least 4 characters long"

        data = self._load_users_data()
        if username not in data.get("users", {}):
            return False, f"User '{username}' does not exist"

        salt = secrets.token_hex(16)
        pass_hash = self._hash_password(new_password, salt)
        data["users"][username]["password_hash"] = pass_hash
        data["users"][username]["salt"] = salt
        data["users"][username]["updated_at"] = int(time.time())

        self._save_users_data(data)
        return True, "Password updated successfully"

    def update_role(self, username: str, new_role: str) -> Tuple[bool, str]:
        """Updates the role for an existing user."""
        if new_role not in ROLE_PERMISSIONS:
            return False, f"Invalid role '{new_role}'. Allowed roles: {', '.join(ROLE_PERMISSIONS.keys())}"

        data = self._load_users_data()
        if username not in data.get("users", {}):
            return False, f"User '{username}' does not exist"

        # Prevent removing SuperAdmin role from last administrator
        if data["users"][username]["role"] == "SuperAdmin" and new_role != "SuperAdmin":
            admin_count = sum(1 for u in data["users"].values() if u.get("role") == "SuperAdmin")
            if admin_count <= 1:
                return False, "Cannot demote the last remaining SuperAdmin"

        data["users"][username]["role"] = new_role
        data["users"][username]["updated_at"] = int(time.time())
        self._save_users_data(data)
        return True, "Role updated successfully"

    def delete_user(self, username: str) -> Tuple[bool, str]:
        """Deletes a user account."""
        data = self._load_users_data()
        if username not in data.get("users", {}):
            return False, f"User '{username}' does not exist"

        if data["users"][username]["role"] == "SuperAdmin":
            admin_count = sum(1 for u in data["users"].values() if u.get("role") == "SuperAdmin")
            if admin_count <= 1:
                return False, "Cannot delete the last remaining SuperAdmin"

        del data["users"][username]
        self._save_users_data(data)

        # Invalidate active sessions for this user
        self.revoke_user_sessions(username)
        return True, "User deleted successfully"

    # --------------------------------------------------------------------------
    # AUTHENTICATION & SESSION MANAGEMENT
    # --------------------------------------------------------------------------

    def authenticate(self, username: str, password: str) -> Optional[Dict[str, Any]]:
        """
        Validates username and password. On success, creates a new session
        and returns a session payload with session_token and csrf_token.
        """
        data = self._load_users_data()
        user = data.get("users", {}).get(username)
        if not user:
            # Constant-time dummy computation to mitigate timing attacks
            self._hash_password("dummy", secrets.token_hex(16))
            return None

        salt = user.get("salt", "")
        expected_hash = user.get("password_hash", "")
        computed_hash = self._hash_password(password, salt)

        # Constant-time comparison
        if not secrets.compare_digest(expected_hash, computed_hash):
            return None

        # Clean expired sessions
        self._cleanup_expired_sessions()

        # Create session
        session_token = secrets.token_hex(32)
        csrf_token = secrets.token_hex(32)
        now = time.time()
        
        session_record = {
            "session_token": session_token,
            "csrf_token": csrf_token,
            "username": username,
            "role": user.get("role", "Operator"),
            "created_at": now,
            "expires_at": now + self.SESSION_TTL_SECONDS
        }
        self.sessions[session_token] = session_record

        return {
            "session_token": session_token,
            "csrf_token": csrf_token,
            "username": username,
            "role": user.get("role", "Operator"),
            "expires_at": session_record["expires_at"]
        }

    def validate_session(self, session_token: str) -> Optional[Dict[str, Any]]:
        """
        Validates an existing session token. If valid, refreshes sliding expiration
        and returns the session dictionary.
        """
        if not session_token or session_token not in self.sessions:
            return None

        sess = self.sessions[session_token]
        now = time.time()
        if now > sess["expires_at"]:
            del self.sessions[session_token]
            return None

        # Sliding expiration refresh
        sess["expires_at"] = now + self.SESSION_TTL_SECONDS
        return sess

    def revoke_session(self, session_token: str) -> bool:
        """Terminates an active session."""
        if session_token in self.sessions:
            del self.sessions[session_token]
            return True
        return False

    def revoke_user_sessions(self, username: str) -> None:
        """Terminates all active sessions for a specific username."""
        to_delete = [tok for tok, s in self.sessions.items() if s["username"] == username]
        for tok in to_delete:
            self.sessions.pop(tok, None)

    def validate_csrf(self, session_token: str, csrf_token: str) -> bool:
        """Validates that the provided CSRF token matches the session."""
        sess = self.validate_session(session_token)
        if not sess:
            return False
        return secrets.compare_digest(sess.get("csrf_token", ""), csrf_token)

    def _cleanup_expired_sessions(self) -> None:
        """Prunes expired sessions from memory."""
        now = time.time()
        expired = [tok for tok, s in self.sessions.items() if now > s["expires_at"]]
        for tok in expired:
            self.sessions.pop(tok, None)

    # --------------------------------------------------------------------------
    # RBAC AUTHORIZATION CHECK
    # --------------------------------------------------------------------------

    def has_permission(self, username_or_role: str, permission: str) -> bool:
        """
        Checks if a user or role has a specific permission.
        """
        role = username_or_role
        # If it's not a known role name, look up role for this username
        if role not in ROLE_PERMISSIONS:
            data = self._load_users_data()
            u = data.get("users", {}).get(username_or_role)
            if not u:
                return False
            role = u.get("role", "")

        perms = ROLE_PERMISSIONS.get(role, set())
        return permission in perms
