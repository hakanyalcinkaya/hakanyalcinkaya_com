from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env(
    DEBUG=(bool, False),
)
env.read_env(BASE_DIR / ".env")

if env("DEBUG"):
    from .settings_dev import *  # noqa: F403
    print(
        f"{'*' * 30}\n{' Django ':-^30}\n{' Debug : ' + str(DEBUG) + ' ':-^30}\n{'*' * 30}"
    )
else:
    from .settings_prod import *  # noqa: F403
