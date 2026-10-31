# Otomatik güncelleme (GitHub Actions → SSH → deploy.sh)

`main` dalına push edildiğinde GitHub Actions sunucuya SSH ile bağlanır ve `_server/deploy.sh` çalışır. Betik
yeni commit'leri çeker ve **yalnız gereken işi** yapar: hangi servisin yeniden başlayacağı değişen dosyalardan çıkar
(liste `deploy.sh`'nin başında). Push her zaman elle yapılır.

```
git push (elle) ──► GitHub Actions (.github/workflows/deploy.yml)
                        │  ssh deploy@sunucu (yalnız deploy betiğini çalıştırabilen anahtar)
                        ▼
                 sunucu: _server/deploy.sh ──► git fetch + merge --ff-only
                                             ├─ pip install      (requirements.txt değiştiyse)
                                             ├─ migrate          (migrations değiştiyse)
                                             ├─ collectstatic    (static_files değiştiyse)
                                             ├─ uWSGI reload     (her seferinde, kesintisiz)
                                             ├─ Celery restart   (.py değiştiyse)
                                             └─ Nginx reload     (nginx config değiştiyse)
```

> **Ortak uWSGI'ye dokunulmaz.** Sunucuda başka siteler de aynı uWSGI Emperor'u (`uwsgi.service`) kullanır.
> Deploy yalnız bu sitenin kendi dosyalarını `touch` eder (`reload.txt`, `/etc/uwsgi/sites/hakanyalcinkaya.ini`);
> `uwsgi.service` düzenlenmez, `systemctl restart uwsgi` çalıştırılmaz, sudoers'ta da buna izin verilmez.

**Kim ne yapar:** Sunucu root ile yönetilir, deploy ise sudo grubunda olmayan ayrı bir `deploy` kullanıcısıyla
yapılır. Kod, venv ve `static_files` `deploy`'a aittir; uygulamanın yazdığı `media_files` ve `log` `www-data`'da
kalır. Böylece Actions anahtarı ele geçse bile zarar `deploy`'un dosyaları ve sudoers'taki dört komutla sınırlı kalır.

Adımlardaki örnekler: sunucu `hakanyalcinkaya.com`, SSH portu `PORT` (sunucuda `sshd -T | grep '^port '`; 22
olmayabilir). Kurulum `README.md`'deki adımlar bittikten sonra yapılır; 1–5 sunucuda root ile.

---

## 1. Deploy kullanıcısı

```bash
adduser --disabled-password --gecos "" deploy      # şifresiz, sudo grubuna eklenmez
sshd -T | grep -iE '^(port|allowusers|allowgroups) '   # AllowUsers/AllowGroups varsa deploy eklenmeli
```

## 2. Sahiplikler

Önce repo içinde root'a ait olmayan dosya var mı bak (çıktı boş olmalı; varsa ayrı tutulur):

```bash
find /var/www/hakanyalcinkaya/hakanyalcinkaya_dj -not -user root -not -path '*/.git/*' | head
```

```bash
chown -R deploy:deploy /var/www/hakanyalcinkaya/hakanyalcinkaya_dj /var/Env/hakanyalcinkaya_312 /var/www/hakanyalcinkaya/static_cdn/static_files
chown deploy:www-data /var/www/hakanyalcinkaya/hakanyalcinkaya_dj/.env && chmod 640 /var/www/hakanyalcinkaya/hakanyalcinkaya_dj/.env
sudo -u www-data cat /var/www/hakanyalcinkaya/hakanyalcinkaya_dj/manage.py > /dev/null && echo okunuyor
```

`media_files` ve `log` `www-data:www-data` kalır.

## 3. Deploy kullanıcısı GitHub'dan çekebiliyor mu

Repo public olduğu için HTTPS ile anahtarsız çekilir; sunucuda GitHub anahtarı gerekmez.

```bash
sudo -u deploy -H bash
cd /var/www/hakanyalcinkaya/hakanyalcinkaya_dj
git remote -v                           # https://github.com/hakanyalcinkaya/hakanyalcinkaya_com.git
git fetch origin main && echo tamam     # şifre sormadan
git rev-parse --is-shallow-repository   # false (sürüm numarası v178 tam geçmişle sayılır); true ise: git fetch --unshallow
git status --short                      # boş olmalı; " M" varsa --ff-only birleştirme durur
ls -l reload.txt _server/deploy.sh      # ikisi de deploy'un, deploy.sh çalıştırılabilir (x)
exit
```

Root ile bu repoda git çalıştırılırsa `detected dubious ownership` hatası gelir. Önerilen `safe.directory`
**eklenmez**: root'un yazdığı dosyalar sonraki deploy'ları bozar (bkz. "Sunucuda elle iş").

## 4. Log dosyası

Log klasörü `www-data`'nındır; deploy kullanıcısı kendi dosyasına yazar:

```bash
touch /var/www/hakanyalcinkaya/log/deploy.log
chown deploy:deploy /var/www/hakanyalcinkaya/log/deploy.log
sudo -u deploy sh -c 'echo test >> /var/www/hakanyalcinkaya/log/deploy.log' && echo yazabiliyor
```

## 5. Şifresiz sudo (yalnız gereken komutlar)

Betik Celery'yi yeniden başlatmak, servis dosyası değişince `daemon-reload` ve Nginx'i yeniden yüklemek için sudo
kullanır. Yalnız bu komutlara şifresiz izin verilir (`_server/sudoers-deploy`):

```bash
which systemctl nginx    # /usr/bin/systemctl, /usr/sbin/nginx; farklıysa sudoers-deploy düzeltilir
sed 's/DEPLOY_USER/deploy/' /var/www/hakanyalcinkaya/hakanyalcinkaya_dj/_server/sudoers-deploy > /etc/sudoers.d/hakanyalcinkaya-deploy
chmod 440 /etc/sudoers.d/hakanyalcinkaya-deploy
visudo -cf /etc/sudoers.d/hakanyalcinkaya-deploy    # "parsed OK"; değilse dosya hemen silinir
```

Kontrol:

```bash
sudo -u deploy sudo -n /usr/sbin/nginx -t                                            # test is successful
sudo -u deploy sudo -n /usr/bin/systemctl restart hakanyalcinkaya-celery && echo izin-tamam
sudo -u deploy sudo -n /usr/bin/systemctl restart uwsgi    # "a password is required" olmalı (ortak uWSGI)
```

`nginx -t`'deki `uwsgi_params_hash` uyarısı deploy'u durdurmaz; yalnız hata durdurur.

## 6. GitHub Actions için SSH anahtarı (kendi bilgisayarında)

Bu anahtar yalnız GitHub'a verilir; sunucuya **genel** (public) kısmı eklenir.

```bash
ssh-keygen -t ed25519 -C "github-actions-deploy@hakanyalcinkaya.com" -f ~/.ssh/hy_github_actions -N ""
cat ~/.ssh/hy_github_actions.pub     # 6b'de sunucuya
ssh-keygen -lf ~/.ssh/hy_github_actions.pub   # parmak izi, 6b'de karşılaştırılır
```

### 6b. Anahtarı deploy kullanıcısına kısıtlı olarak ekle (sunucuda, root)

Satırın başındaki `restrict,command="..."` sayesinde bu anahtarla yalnız deploy betiği çalışır; terminal, port
yönlendirme ya da başka komut açılamaz.

```bash
install -d -m 700 -o deploy -g deploy /home/deploy/.ssh
# tek satır; ssh-ed25519 ... kısmı 6'daki .pub dosyasının içeriği:
echo 'restrict,command="/var/www/hakanyalcinkaya/hakanyalcinkaya_dj/_server/deploy.sh" ssh-ed25519 AAAA...BURAYA... github-actions-deploy@hakanyalcinkaya.com' >> /home/deploy/.ssh/authorized_keys
chown deploy:deploy /home/deploy/.ssh/authorized_keys && chmod 600 /home/deploy/.ssh/authorized_keys
ssh-keygen -lf /home/deploy/.ssh/authorized_keys   # 6'daki parmak iziyle aynı
```

## 7. Sunucunun SSH parmak izi (known_hosts) ve bağlantı denemesi

GitHub'ın bağlandığı sunucunun gerçekten seninki olduğunu doğrulaması için:

```bash
# Kendi bilgisayarında (port sshd'nin portu):
ssh-keyscan -p PORT -t ed25519 hakanyalcinkaya.com 2>/dev/null > hy_known_hosts
ssh-keygen -lf hy_known_hosts
# Sunucuda aynı parmak izi görünmeli:
ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub
```

İkisi aynıysa `hy_known_hosts`'taki satır (`[hakanyalcinkaya.com]:PORT ssh-ed25519 AAAA...`; port 22 ise köşeli
parantezsiz) adım 8'de `DEPLOY_KNOWN_HOSTS` olur. Satırdaki ad `DEPLOY_HOST` ile aynı olmalı: IP kullanılacaksa
keyscan de IP ile yapılır. Keyscan boş dönerse (`Broken pipe`) port yanlıştır.

Actions'ın yapacağı bağlantıyı aynı ayarlarla dene:

```bash
ssh -i ~/.ssh/hy_github_actions -p PORT -o BatchMode=yes -o StrictHostKeyChecking=yes -o IdentitiesOnly=yes \
    -o UserKnownHostsFile=hy_known_hosts deploy@hakanyalcinkaya.com; echo "exit $?"
# → "deploy başladı", "Yeni commit yok (v178 abc1234).", exit 0
#   Baştaki "PTY allocation request failed" restrict'ten gelir, beklenen.
ssh -i ~/.ssh/hy_github_actions -p PORT -o IdentitiesOnly=yes -o UserKnownHostsFile=hy_known_hosts \
    deploy@hakanyalcinkaya.com 'whoami; ls /'
# → whoami/ls çıktısı değil, yine yalnız deploy çıktısı (anahtar başka komut çalıştıramaz)
```

## 8. GitHub'da ortam ve Secrets

1. GitHub → repo → **Settings → Environments** → `production` (yoksa **New environment**; ilk push'taki
   workflow da otomatik açar).
2. **Deployment branches and tags** → **Selected branches and tags** → **Add deployment branch or tag rule** →
   Branch, `main`. Seçenek açılıp kural eklenmezse hiçbir dal deploy edemez.
   **Required reviewers** isteğe bağlı (her deploy onay bekler).
3. `production` ortamına **Environment secrets** ekle (repo seviyesindeki Actions secrets'a değil):

| Secret | Değer |
|---|---|
| `DEPLOY_HOST` | `hakanyalcinkaya.com` (known_hosts satırındaki adla aynı) |
| `DEPLOY_USER` | `deploy` |
| `DEPLOY_PORT` | sshd'nin portu (boş bırakılırsa 22) |
| `DEPLOY_SSH_KEY` | `~/.ssh/hy_github_actions` dosyasının **tamamı** (`-----BEGIN ... END-----` dahil): `pbcopy < ~/.ssh/hy_github_actions` |
| `DEPLOY_KNOWN_HOSTS` | adım 7'deki `hy_known_hosts` satırı |

Kontrol (`gh` ile; değerler okunamaz, yalnız adlar):

```bash
gh secret list --repo hakanyalcinkaya/hakanyalcinkaya_com --env production
gh api repos/hakanyalcinkaya/hakanyalcinkaya_com/environments/production/deployment-branch-policies --jq '.branch_policies[].name'   # main
```

## 9. İlk deneme

1. GitHub → **Actions → Deploy → Run workflow** (main) ya da
   `gh workflow run deploy.yml --repo hakanyalcinkaya/hakanyalcinkaya_com --ref main`. Push etmeden betiği bir kez
   çalıştırır.
2. Çıktıda `Yeni commit yok (v178 abc1234)` ya da değişen dosyalar ve yapılan işler görünür.
3. Sunucuda: `tail -n 50 /var/www/hakanyalcinkaya/log/deploy.log`
4. Siteye superuser olarak gir: kullanıcı menüsündeki ve Stüdyo'daki **v178** numarası yereldekiyle
   (`git rev-list --count HEAD`) aynı olmalı. Numara deploy'un yazdığı `.version` dosyasından okunur
   (`cat .version` → `v178 abc1234`); uygulama `www-data` ile çalıştığı için `.git`'e bakmasına gerek kalmaz.
5. Küçük bir commit push et; Actions kendiliğinden çalışmalı.

Hepsi tamamsa yerel kopyadaki özel anahtarı ve `hy_known_hosts`'u sil (anahtar yalnız GitHub'da kalsın):
`rm ~/.ssh/hy_github_actions ~/.ssh/hy_github_actions.pub hy_known_hosts`

## Günlük kullanım

- Yerelde commit, sonra elle `git push origin main` → birkaç dakika içinde site güncellenir (Actions sekmesinde izlenir).
- **Sürüm kontrolü:** superuser menüde `vNNN` görür (commit sayısı; üstüne gelince kısa commit kimliği). Yerel ve
  sunucu numarası aynıysa ikisi aynı commit'te; sunucunun numarası küçükse henüz deploy olmamış commit var.
- **Deploy istemiyorsan:** commit mesajına `[skip ci]` yaz.
- **Her şeyi yeniden başlat:** commit mesajına `[restart all]` (pip, migrate, collectstatic, uWSGI, Celery, Nginx).
- **Geri almak:** sunucuda elle geri sarma yok (`--ff-only`); hatalı commit yerelde `git revert` ile geri alınıp push edilir.
- **Celery ve video yüklemesi:** `.py` değişen her deploy'da Celery yeniden başlar; süren yükleme en fazla 60 sn
  (servisteki `TimeoutStopSec`) bitirilmeye çalışılır, yarıda kalırsa stüdyodan "Yeniden dene". Uzun yükleme
  sürerken push etmemek en güvenlisi.
- **Actions log'unda `*** başladı`:** `DEPLOY_USER` secret'ının değeri (`deploy`) log'da her yerde gizlenir; zararsız.

## Sunucuda elle iş

Git, `manage.py`, `pip` ve `deploy.sh` her zaman `deploy` kullanıcısıyla çalıştırılır; root ile yalnız sudoers,
sahiplik ve servis işleri yapılır. Root'un açtığı venv (`(hakanyalcinkaya_312)` istemi) de kapatılır (`deactivate`):
root'un yazdığı dosyalar (venv, `.git`, `static_files`, `.version`) sonraki deploy'ları `Permission denied` ile durdurur.

```bash
sudo -u deploy -H bash
cd /var/www/hakanyalcinkaya/hakanyalcinkaya_dj
bash _server/deploy.sh                         # elle deploy (yeni commit yoksa .version yazılır, eksik ikon dosyaları üretilir)
/var/Env/hakanyalcinkaya_312/bin/python manage.py shell
```

## Sorun giderme

| Belirti | Neden / çözüm |
|---|---|
| Actions'ta `Permission denied (publickey)` | `DEPLOY_SSH_KEY` eksik/yanlış ya da 6b'deki satır `/home/deploy/.ssh/authorized_keys`'te yok |
| `Host key verification failed` | `DEPLOY_KNOWN_HOSTS` eksik, `DEPLOY_HOST` satırdaki adla aynı değil ya da sunucunun anahtarı değişti (adım 7) |
| `Connection refused` / zaman aşımı | `DEPLOY_PORT` sshd'nin portu değil (`sshd -T \| grep '^port '`) |
| `Branch "main" is not allowed to deploy to production` | Adım 8.2: ortamda `main` kuralı yok |
| `Not possible to fast-forward` | Sunucuda elle değiştirilmiş dosya var: `git status` (deploy kullanıcısıyla); değişiklik geri alınır ya da commit'e taşınır |
| `detected dubious ownership` | Git root ile çalıştırıldı; `sudo -u deploy -H` ile çalıştır |
| `Permission denied` (venv, `.git`, `static_files`, `.version`) | Root'un yazdığı dosya kalmış: `chown -R deploy:deploy` ile ilgili yol (adım 2) |
| `sudo: a password is required` | Adım 5; komut yolu sudoers'takiyle birebir aynı olmalı |
| `deploy.log: Permission denied` | Adım 4 |
| Menüde sürüm yok ya da eski | Sunucu elle `git pull` ile güncellendiyse `.version` yenilenmez: deploy kullanıcısıyla `bash _server/deploy.sh` |
| Site açılmıyor (502) | `journalctl -u uwsgi -n 50`, `tail /var/www/hakanyalcinkaya/log/uwsgi.log` |
