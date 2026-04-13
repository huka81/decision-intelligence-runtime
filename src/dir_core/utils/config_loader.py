"""
Unified YAML config loading for DIR/ROA samples.

All samples that load config.yaml should use load_yaml_config() for consistency.
Requires PyYAML: pip install pyyaml
"""

from pathlib import Path
from typing import Any, Dict, Union


def load_yaml_config(path: Union[Path, str]) -> Dict[str, Any]:
    """
    Load and parse a YAML config file. Returns raw dict.

    Args:
        path: Path to the YAML file.

    Returns:
        Parsed YAML as dict. Empty dict if file is empty or null.

    Raises:
        ImportError: If PyYAML is not installed.
        FileNotFoundError: If the file does not exist.
        ValueError: If the file content is not a valid YAML mapping (dict).
    """
    try:
        import yaml
    except ImportError:
        raise ImportError("YAML config requires PyYAML. Install with: pip install pyyaml")

    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    with path.open(encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ValueError(f"Config file must be a YAML mapping (dict), got {type(raw).__name__}")

    return raw
