import os
import json

def load_settings(custom_path=None):
    """
    Loads configuration settings from config/settings.json or a custom path.
    """
    if custom_path:
        settings_path = custom_path
    else:
        # Derive path from __file__ so it works regardless of cwd
        _dir = os.path.dirname(os.path.abspath(__file__))
        settings_path = os.path.normpath(os.path.join(_dir, "..", "config", "settings.json"))

    if os.path.exists(settings_path):
        try:
            with open(settings_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"Warning: Failed to load {settings_path}: {e}")
    return {}

def normalize_hostname(name, fmt='simple'):
    """
    Returns the normalized hostname: 'simple' (pre-dot) or 'fqdn' (full).
    """
    if not name:
        return ""
    if fmt == 'fqdn':
        return name.strip().upper()
    return name.split('.')[0].strip().upper()
