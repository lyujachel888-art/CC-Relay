import os
from dataclasses import dataclass
from dotenv import load_dotenv


@dataclass
class Config:
    app_id: str
    app_secret: str
    user_open_id: str


def load_config() -> Config:
    load_dotenv()
    return Config(
        app_id=os.environ["FEISHU_APP_ID"],
        app_secret=os.environ["FEISHU_APP_SECRET"],
        user_open_id=os.environ["FEISHU_USER_OPEN_ID"],
    )
