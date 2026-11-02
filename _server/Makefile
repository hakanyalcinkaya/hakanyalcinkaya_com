# hakanyalcinkaya.com servislerini sunucuda elle yeniden başlatma. Proje klasöründen:
#     make -C _server              # hedeflerin listesi
#     make -C _server uwsgi-celery
#
# root ya da deploy kullanıcısıyla çalışır. root'ken dosyalar deploy kullanıcısıyla touch edilir (root'a ait dosya
# sonraki deploy'u bozar); deploy kullanıcısı sudo ile yalnız _server/sudoers-deploy'daki komutları çalıştırabilir
# (redis ve postgresql hedefleri root ister).
#
# Ortak uWSGI Emperor'a (uwsgi.service; sunucudaki diğer siteler) dokunulmaz: yalnız bu sitenin dosyaları touch edilir.

APP_DIR      := /var/www/hakanyalcinkaya/hakanyalcinkaya_dj
UWSGI_VASSAL := /etc/uwsgi/sites/hakanyalcinkaya.ini
CELERY       := hakanyalcinkaya-celery
DEPLOY_USER  := deploy
SYSTEMCTL    := /usr/bin/systemctl
NGINX        := /usr/sbin/nginx

ifeq ($(shell id -u),0)
SUDO      :=
AS_DEPLOY := sudo -u $(DEPLOY_USER)
else
SUDO      := sudo
AS_DEPLOY :=
endif

.DEFAULT_GOAL := help
.PHONY: help uwsgi uwsgi-ini celery celery-unit nginx uwsgi-celery uwsgi-celery-nginx all redis postgresql status logs

help:
	@echo "Bu site:"
	@echo "  make uwsgi               uWSGI kesintisiz yeniden yüklenir (kod, şablon, .env değişince)"
	@echo "  make celery              Celery yeniden başlar (görev kodu, .env); süren video yüklemesi yarıda kalır"
	@echo "  make nginx               nginx -t, sonra reload (bağlantılar kopmaz)"
	@echo "  make uwsgi-celery        uwsgi + celery"
	@echo "  make uwsgi-celery-nginx  uwsgi + celery + nginx"
	@echo "  make all                 servis dosyalarını yeniden oku + uwsgi-ini + celery + nginx"
	@echo "Dosya değişikliğinden sonra:"
	@echo "  make uwsgi-ini           _server/hakanyalcinkaya_uwsgi.ini değişti: Emperor siteyi yeniden açar"
	@echo "  make celery-unit         _server/celery/*.service değişti: daemon-reload + celery"
	@echo "Ortak servisler (diğer sitelerdeki bağlantılar da kopar; onay ister, root):"
	@echo "  make redis               redis-server restart (Celery kuyruğu, önbellek, oturum sınırları)"
	@echo "  make postgresql          postgresql restart"
	@echo "Kontrol:"
	@echo "  make status              servislerin durumu ve sitenin yanıtı"
	@echo "  make logs                uwsgi, celery ve nginx hata logları (Ctrl+C ile çık)"

uwsgi:
	@echo "→ uWSGI yeniden yükleniyor (reload.txt)"
	$(AS_DEPLOY) touch $(APP_DIR)/reload.txt

uwsgi-ini:
	@echo "→ uWSGI sitesi yeniden açılıyor ($(UWSGI_VASSAL))"
	$(AS_DEPLOY) touch $(UWSGI_VASSAL)

celery:
	@echo "→ Celery yeniden başlıyor"
	$(SUDO) $(SYSTEMCTL) restart $(CELERY)

celery-unit:
	@echo "→ systemd servis dosyaları yeniden okunuyor"
	$(SUDO) $(SYSTEMCTL) daemon-reload
	@$(MAKE) --no-print-directory celery

nginx:
	@echo "→ Nginx config kontrolü ve reload"
	$(SUDO) $(NGINX) -t
	$(SUDO) $(SYSTEMCTL) reload nginx

uwsgi-celery: uwsgi celery

uwsgi-celery-nginx: uwsgi celery nginx

all: celery-unit uwsgi-ini nginx

redis:
	@read -p "redis-server yeniden başlatılsın mı? Sunucudaki diğer projeler de etkilenir. [e/H] " answer; [ "$$answer" = "e" ]
	$(SUDO) $(SYSTEMCTL) restart redis-server

postgresql:
	@read -p "postgresql yeniden başlatılsın mı? Sunucudaki diğer sitelerin veritabanı bağlantıları da kopar. [e/H] " answer; [ "$$answer" = "e" ]
	$(SUDO) $(SYSTEMCTL) restart postgresql
	@echo "Bağlantılar uWSGI ve Celery'de kendiliğinden yenilenmezse: make uwsgi-celery"

status:
	@for service in uwsgi $(CELERY) nginx redis-server postgresql; do \
		printf "%-24s %s\n" "$$service" "$$($(SYSTEMCTL) is-active $$service)"; \
	done
	@ls -l /run/uwsgi/hakanyalcinkaya.sock
	@curl -sI https://hakanyalcinkaya.com | head -1

logs:
	tail -n 30 -f /var/www/hakanyalcinkaya/log/uwsgi.log /var/log/celery/hakanyalcinkaya.log /var/log/nginx/hakanyalcinkaya_error.log
