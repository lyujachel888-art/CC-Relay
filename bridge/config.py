import os
from dataclasses import dataclass
from pathlib import Path
from dotenv import find_dotenv, load_dotenv


@dataclass
class Config:
    app_id: str
    app_secret: str
    user_open_id: str


def load_config() -> Config:
    plugin_env_path = Path.home() / ".claude" / "plugins" / "cc-relay" / ".env"
    if plugin_env_path.exists():
        load_dotenv(plugin_env_path)
    else:
        load_dotenv(find_dotenv(usecwd=True))   # fallback: cwd .env (dev workflow)
    return Config(
        app_id=os.environ["FEISHU_APP_ID"],
        app_secret=os.environ["FEISHU_APP_SECRET"],
        user_open_id=os.environ["FEISHU_USER_OPEN_ID"],
    )
