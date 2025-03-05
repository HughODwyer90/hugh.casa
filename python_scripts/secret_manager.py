import yaml
import os

class SecretsManager:
    """Manages the dynamic loading and retrieval of secrets from a YAML file."""
    
    def __init__(self, secrets_file_path='/config/secrets.yaml'):
        self.secrets_file_path = secrets_file_path
        self._secrets = {}  # Store secrets dynamically
        self.load_secrets()

    def load_secrets(self):
        """Loads secrets from YAML file and caches them."""
        try:
            with open(self.secrets_file_path, "r") as file:
                self._secrets = yaml.safe_load(file) or {}  # Ensure a dictionary is returned
        except FileNotFoundError:
            raise FileNotFoundError(f"Error: {self.secrets_file_path} not found.")
        except yaml.YAMLError as e:
            raise ValueError(f"Error parsing {self.secrets_file_path}: {e}")

    def reload(self):
        """Reloads secrets from file (useful if secrets.yaml changes)."""
        self.load_secrets()

    def get(self, key, default=None):
        """Retrieves a secret with optional default value. Supports environment variable override."""
        return os.getenv(key.upper(), self._secrets.get(key, default))  # Allows env vars to override secrets

    def __getitem__(self, key):
        """Allows dictionary-like access: secrets['key']"""
        return self.get(key)

    def __contains__(self, key):
        """Allows 'key' in secrets checking."""
        return key in self._secrets or key.upper() in os.environ

    def keys(self):
        """Returns all available secret keys."""
        return list(self._secrets.keys())

    def values(self):
        """Returns all secret values (excluding environment overrides)."""
        return list(self._secrets.values())

    def items(self):
        """Returns all secret key-value pairs (excluding environment overrides)."""
        return self._secrets.items()



