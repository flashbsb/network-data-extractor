import os
import json

def deep_merge(target: dict, source: dict) -> dict:
    """Recursively merges source dict into target dict."""
    for key, value in source.items():
        if key in target and isinstance(target[key], dict) and isinstance(value, dict):
            deep_merge(target[key], value)
        else:
            target[key] = value
    return target


def load_settings(custom_path=None):
    """
    Loads configuration settings. Supports both monolithic settings.json and
    modular configuration files (*.json in the config directory).
    Modular configs are deep-merged on top of base settings.json.
    """
    config = {}

    if custom_path:
        if os.path.isdir(custom_path):
            config_dir = os.path.abspath(custom_path)
            base_settings_file = os.path.join(config_dir, "settings.json")
        else:
            base_settings_file = os.path.abspath(custom_path)
            config_dir = os.path.dirname(base_settings_file)
    else:
        _dir = os.path.dirname(os.path.abspath(__file__))
        config_dir = os.path.normpath(os.path.join(_dir, "..", "config"))
        base_settings_file = os.path.join(config_dir, "settings.json")

    # 1. Load legacy/base settings.json if present
    if os.path.isfile(base_settings_file):
        try:
            with open(base_settings_file, "r", encoding="utf-8") as f:
                loaded = json.load(f)
                if isinstance(loaded, dict):
                    config = loaded
        except Exception as e:
            print(f"Warning: Failed to load {base_settings_file}: {e}")

    # 2. Discover and deep-merge modular configuration files (*.json)
    if os.path.isdir(config_dir):
        # Specific preferred order to guarantee deterministic merge precedence
        preferred_order = ["extractor.json", "ssh.json", "network.json", "ping.json", "storage.json"]
        found_files = [f for f in os.listdir(config_dir) if f.endswith(".json") and f != "settings.json"]
        
        # Sort by preferred order first, then alphabetically
        def sort_key(name):
            try:
                return (0, preferred_order.index(name))
            except ValueError:
                return (1, name)

        for filename in sorted(found_files, key=sort_key):
            file_path = os.path.join(config_dir, filename)
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    mod_data = json.load(f)
                    if isinstance(mod_data, dict):
                        deep_merge(config, mod_data)
            except Exception as e:
                print(f"Warning: Failed to merge modular config {file_path}: {e}")

    return config
def normalize_hostname(name, fmt='simple'):
    """
    Returns the normalized hostname: 'simple' (pre-dot) or 'fqdn' (full).
    """
    if not name:
        return ""
    if fmt == 'fqdn':
        return name.strip().upper()
    return name.split('.')[0].strip().upper()
