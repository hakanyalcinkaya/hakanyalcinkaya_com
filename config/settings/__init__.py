from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env(
    DEBUG=(bool, False),
)
# overwrite: uWSGI reload.txt ile yeniden yüklenirken eski ortam değişkenleri süreçte kalır; .env'deki yeni değer
# onları ezmeli. (.env'den silinen değişken süreçte kalır; onun için siteyi sıfırdan başlatmak gerekir.)
env.read_env(BASE_DIR / ".env", overwrite=True)

if env("DEBUG"):
    from .settings_dev import *  # noqa: F403
    print(
        f"{'*' * 30}\n{' Django ':-^30}\n{' Debug : ' + str(DEBUG) + ' ':-^30}\n{'*' * 30}"
    )
else:
    from .settings_prod import *  # noqa: F403
