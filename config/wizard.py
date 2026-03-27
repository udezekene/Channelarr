"""Interactive first-run setup wizard.

Prompts the user for their Dispatcharr credentials, writes config.yaml,
and returns the resulting Config instance.
"""

from getpass import getpass
from pathlib import Path
from config.schema import Config
from config import loader


def run(path: Path | None = None) -> Config:
    """Walk the user through initial setup and write config.yaml."""
    print("\nChannelarr — first-time setup")
    print("─" * 40)
    print("You can edit the config file afterwards to add locks, allowlists,")
    print("blocklists, and matching options.\n")

    endpoint = input("Dispatcharr URL [http(s)://HOST:PORT]: ").strip()
    username = input("Username: ").strip()
    password = getpass("Password: ").strip()

    config = Config(endpoint=endpoint, username=username, password=password)
    loader.write(config, path)

    config_path = path or loader.DEFAULT_CONFIG_PATH
    print(f"\nConfig saved to {config_path}\n")

    return config
