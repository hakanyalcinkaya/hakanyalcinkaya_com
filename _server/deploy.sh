#!/usr/bin/env bash
# hakanyalcinkaya.com otomatik güncelleme: GitHub Actions (main'e push) SSH ile bu betiği çalıştırır.
# Elle de çalıştırılabilir: bash /var/www/hakanyalcinkaya/hakanyalcinkaya_dj/_server/deploy.sh
#
# Yalnız gereken iş yapılır; ne yapılacağı eski ve yeni commit arasında değişen dosyalardan çıkar:
#   her güncellemede          → uWSGI kesintisiz yeniden yüklenir (touch reload.txt)
#   requirements.txt          → pip install (+ collectstatic, uWSGI, Celery)
#   */migrations/*            → migrate
#   static_files/**           → collectstatic
#   *.html, *.js, *.py, *.css → build_icons (kullanılan ikonlar; yeniden üretildiyse collectstatic)
#   *.py                      → Celery yeniden başlar (şablon/CSS/JS değişikliğinde başlamaz; süren yükleme kesilmesin)
#   _server/celery/*.service  → systemctl daemon-reload + Celery
#   _server/*nginx.conf       → nginx -t && reload (restart değil; bağlantılar kopmaz)
#   _server/*uwsgi.ini        → Emperor siteyi yeniden açar
# Commit mesajında [restart all] varsa hepsi yapılır.
# Güncelleme bu betiği de değiştirdiyse işin geri kalanı betiğin yeni sürümüyle yapılır (kendini --from <eski commit> ile
# yeniden başlatır); yeni adımlar ilk deploy'da çalışır. Yeni commit olmasa da eksik ikon dosyaları üretilir.
# Ortak uWSGI Emperor'a (uwsgi.service; sunucudaki diğer siteler) dokunulmaz: yalnız bu sitenin dosyaları touch edilir.
#
# Kurulum ve GitHub/SSH ayarları: _server/DEPLOY.md

set -euo pipefail

APP_DIR=/var/www/hakanyalcinkaya/hakanyalcinkaya_dj
VENV=/var/Env/hakanyalcinkaya_312
LOG=/var/www/hakanyalcinkaya/log/deploy.log
UWSGI_VASSAL=/etc/uwsgi/sites/hakanyalcinkaya.ini

# Betiğin tamamı main çağrılmadan önce okunur: git güncellemesi bu dosyayı değiştirse de çalışan sürüm bozulmaz.
main() {
    local old new changed message all=0
    if [[ "${1:-}" == "--from" ]]; then
        # Eski sürüm güncellemeyi yaptı ve bu sürümü başlattı; çıktı zaten günlüğe gidiyor, git'e yeniden gidilmez.
        old=$2
        cd "$APP_DIR"
        echo "→ deploy betiği değişti; yeni sürümle devam ediliyor"
    else
        exec > >(tee -a "$LOG") 2>&1
        echo "=== $(date '+%F %T') deploy başladı"
        cd "$APP_DIR"
        old=$(git rev-parse HEAD)
        git fetch --quiet origin main
        # Sunucuda elle değiştirilmiş dosya varsa birleştirme durur; hiçbir şey silinmez.
        git merge --ff-only --quiet origin/main
        if ! git diff --quiet "$old" HEAD -- _server/deploy.sh; then
            exec bash "$APP_DIR/_server/deploy.sh" --from "$old"
        fi
    fi
    new=$(git rev-parse HEAD)
    write_version
    if [[ "$old" == "$new" ]]; then
        echo "Yeni commit yok ($(version))."
        # İkon dosyaları git'te değil; eksikse (ilk kurulum, silinmiş klasör) yine de üretilir.
        if [[ ! -f static_files/icons/bootstrap-icons.css ]]; then
            build_icons || true
            echo "→ collectstatic"
            "$VENV/bin/python" manage.py collectstatic --noinput --verbosity 0
            echo "→ uWSGI yeniden yükleniyor"
            touch reload.txt
        fi
        return 0
    fi
    changed=$(git diff --name-only "$old" "$new")
    message=$(git log --format=%B "$old..$new")
    grep -q '\[restart all\]' <<<"$message" && all=1
    echo "$old → $new ($(version))"
    sed 's/^/  /' <<<"$changed"

    has() { [[ $all == 1 ]] || grep -qE "$1" <<<"$changed"; }

    if has '^requirements\.txt$'; then
        echo "→ pip install"
        "$VENV/bin/pip" install --quiet -r requirements.txt
    fi
    # İkon fontu git'te değil (static_files/icons/); kodda kullanılan ikonlar değiştiyse ya da dosya yoksa üretilir.
    local icons=0
    if has '\.(html|js|py|css)$|^requirements\.txt$|^frontend/bootstrap-icons/' || [[ ! -f static_files/icons/bootstrap-icons.css ]]; then
        build_icons && icons=1
    fi
    if has '/migrations/'; then
        echo "→ migrate"
        "$VENV/bin/python" manage.py migrate --noinput
    fi
    if [[ $icons == 1 ]] || has '^static_files/|^requirements\.txt$'; then
        echo "→ collectstatic"
        "$VENV/bin/python" manage.py collectstatic --noinput --verbosity 0
    fi
    if has '^_server/hakanyalcinkaya_uwsgi\.ini$'; then
        echo "→ uWSGI sitesi yeniden açılıyor (Emperor)"
        touch "$UWSGI_VASSAL"
    else
        echo "→ uWSGI yeniden yükleniyor"
        touch reload.txt
    fi
    if has '^_server/celery/.*\.service$'; then
        echo "→ systemctl daemon-reload"
        sudo -n /usr/bin/systemctl daemon-reload
    fi
    if has '\.py$|^requirements\.txt$|^_server/celery/'; then
        echo "→ Celery yeniden başlıyor"
        sudo -n /usr/bin/systemctl restart hakanyalcinkaya-celery
    fi
    if has '^_server/hakanyalcinkaya_nginx\.conf$'; then
        echo "→ Nginx denetleniyor ve yeniden yükleniyor"
        sudo -n /usr/sbin/nginx -t
        sudo -n /usr/bin/systemctl reload nginx
    fi
    echo "=== $(date '+%F %T') deploy bitti ($(version))"
}

# Kullanılan ikonlarla küçük ikon fontu; yeniden üretildiyse 0 (collectstatic gerekir), ikonlar güncelse 1 döner.
build_icons() {
    echo "→ build_icons"
    local out
    out=$("$VENV/bin/python" manage.py build_icons)
    echo "  $out"
    [[ $out == *"yeniden üretildi"* ]]
}

version() {
    echo "v$(git rev-list --count HEAD) $(git rev-parse --short HEAD)"
}

# Uygulama sürümü bu dosyadan okur (core/version.py): www-data .git'i okuyamasa da superuser menüde v178 görür.
write_version() {
    version > "$APP_DIR/.version.tmp" && mv "$APP_DIR/.version.tmp" "$APP_DIR/.version"
}

main "$@"
