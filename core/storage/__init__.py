# -*- coding: utf-8 -*-
"""
Storage Abstraction Layer (SAL) Package
=======================================
Provides multi-driver persistence (Filesystem, SQLite) and routing facade.
"""

from core.storage.interface import StorageDriver
from core.storage.filesystem_driver import FilesystemDriver
from core.storage.sqlite_driver import SQLiteDriver
from core.storage.manager import StorageManager

__all__ = [
    "StorageDriver",
    "FilesystemDriver",
    "SQLiteDriver",
    "StorageManager",
]
