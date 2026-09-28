from dataclasses import dataclass
import json
from pathlib import Path
import sys


@dataclass
class SignatureConfig:
    position: str = "LU Staff"
    staff_name: str = ""
    image_url: str = ""


def application_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def profile_dir() -> Path:
    path = application_dir() / "bot_profile"
    path.mkdir(parents=True, exist_ok=True)
    return path


def settings_path() -> Path:
    return application_dir() / "settings.json"


def load_signature() -> SignatureConfig:
    path = settings_path()
    if not path.exists():
        return SignatureConfig()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return SignatureConfig(
            position=str(data.get("position", "LU Staff")),
            staff_name=str(data.get("staff_name", "")),
            image_url=str(data.get("image_url", "")),
        )
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return SignatureConfig()


def save_signature(config: SignatureConfig) -> None:
    settings_path().write_text(
        json.dumps({
            "position": config.position,
            "staff_name": config.staff_name,
            "image_url": config.image_url,
        }, indent=2),
        encoding="utf-8",
    )
