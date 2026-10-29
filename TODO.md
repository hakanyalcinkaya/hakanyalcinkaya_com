# TODO

Sonraya bırakılan işler. Tamamlananı listeden çıkar.

## Paketler (Bundle)
- [ ] `/bundles/` liste ve `/bundles/<slug>/` detay sayfalarının tasarımı (kurs sayfasının düzeninden türetilebilir).
- [ ] Kurs sayfasının alt kısmında "Bu kurs şu paketlerde de var" bölümü.
- [ ] Sepette paket ve paketin içindeki tek kurs birlikteyse tek kursu sepetten çıkar, bildirim göster.
- [ ] Kullanıcı paketteki bir kursa zaten sahipse paket fiyatından o kurs için ödediği tutarı düş (hediye/manuel ise 0 düşülür, fiyat 0'ın altına inmez).

## Sepet ve indirim
- [ ] Sepeti boşaltan kullanıcılara ileride indirim bildirimi gönder (boşaltılan sepetler silinmeden `emptied` durumunda tutuluyor).
- [ ] Bağlantıyla gelen indirim kodu: `?kod=KOD` oturumda beklet, sepet oluşunca uygula; kurs ve paket sayfalarında "KOD uygulandı" ile indirimli fiyatı göster.
- [ ] iyzico ödeme entegrasyonu (TL, KDV dahil fiyatlar).

## Video (Bunny Stream)
- [ ] CDN token koruması: Bunny panelinde (Stream → kütüphane → Security) "Token Authentication" açılınca imzalı adresi gerçek CDN'de doğrula, sonra `.env`'de `BUNNY_CDN_TOKEN_AUTH=True` yap (kod hazır, `course/bunny.py` `_signed`). Koruma kapalıyken imzalı adres 404 veriyor (beklenen); koruma açılıp ayar açılmazsa videolar oynamaz, ikisi birlikte yapılmalı.
- [ ] İzlenen süreyi her 5 saniyede bir veritabanına yaz ve dersi kaldığı saniyeden aç (`LessonProgress.position_seconds`). "Tamamlandı" işareti, kenar listesi ve ilerleme çubuğu artık gerçek veriden geliyor.
- [ ] Kurs sayfasının tanıtım metinleri (neler öğreneceksin, kimler için ...) aynı slug'lı örnek kurstan geliyor; kurs maddeleri (CourseHighlight) doldurulunca örnek veri kaldırılabilir. Ana sayfa, kurs listesi, sepet ve Eğitimlerim gerçek veride; yayında kurs yokken örnek kurslar görünür.
- [ ] Ders/tanıtım videosu değiştirilince eski video Bunny'de kalıyor; istenirse yeni video hazır olunca eskisini silme seçeneği.
- [ ] Prod: Vimeo HLS bağlantıları önbellekte tutuluyor (`course/vimeo.py` `playback`); prod'da paylaşılan önbellek (Redis) kullanılmalı, şu an varsayılan bellek içi önbellek.
- [ ] Gerçek videoda deneme: 5 sn sonra tamamlandı, oynatıcı tercihleri (hız/kalite/altyazı otomatik kayıt, tam ekran; iPhone Safari'de tam ekran desteklenmeyebilir). Yerelde `http://local.hakanyalcinkaya.com/` (80 portu) üzerinden.
- [ ] Prod: Celery işçisini servis olarak çalıştır (systemd/supervisor), Redis'i ayrı veritabanı numarasıyla kullan; sunucuda büyük dosya yüklemesi için Nginx `client_max_body_size` ve zaman aşımı ayarları.

## Öğrenci araçları (giriş yapmış ve kursu satın almış kullanıcı)
- [ ] Video notu: oynatıcıda "Not ekle" düğmesi; not videonun o anki saniyesine kaydedilir. Oynatıcının ilerleme çubuğunda notların yerinde işaret (mark) görünür; işarete tıklanınca o saniyeye gidilir. `learning.Note` modeline saniye alanı (ör. `position_seconds`) eklenecek.
- [ ] Derslerde not alma şu an kapalı (Studio → Ayarlar); açılmadan önce not kaydetme bağlanmalı (ders sayfasındaki alan örnek, `learning.Note` kullanılmıyor).
- [ ] Veritabanındaki kurslarda erişim artık kurs kaydına (`Enrollment`) bağlı; sepet/ödeme akışı hâlâ örnek (oturumdaki "satın alma"). iyzico ödemesi onaylanınca `Order.mark_paid` kurs kaydını açacak.

## Podia'dan geçiş
- [ ] Django ve Python kurslarını veritabanında aç, sonra aktar: `python manage.py import_podia <dosya.xlsx> --map "React 18.x=<react-slug>" --map "Python ve Django=<django-slug>" --map "İki Eğitmen=<python-slug>" --dry-run`, rapor temizse `--dry-run` olmadan. Tekrar çalıştırılabilir (aynı fatura ikinci kez yazılmaz); geçiş bitene kadar Podia'daki yeni satışlar için yeniden çalıştır.
- [ ] Site yayına alınınca eski müşterilere "Hesabın taşındı" e-postası (`templates/emails/account_migrated`, şablon hazır): gönderim komutu yazılacak (kişi başına bir kez, gönderildi kaydıyla). Şifre bağlantısı Django'nun `PASSWORD_RESET_TIMEOUT` süresi kadar geçerli (varsayılan 3 gün); toplu gönderimde süre uzatılmalı ya da "Şifremi unuttum" yönlendirmesi yeterli.

## E-postalar
- [ ] Şablonlar hazır (`templates/emails/`, önizleme: Stüdyo → E-postalar). Yalnız "Şifremi unuttum" bağlı; diğerleri olaylara bağlanacak: kayıt (hoş geldin), ödeme onayı / başarısız / iade (iyzico), kurs bitirme, yorum onayı, şifre ve e-posta değişikliği, bülten onayı ve bülten, yönetici bildirimleri.
- [ ] Yayına çıkarken `.env`'den `EMAIL_REDIRECT_TO` kaldırılmalı (şu an bütün e-postalar hakanyalcinkaya@gmail.com'a gidiyor) ve `SITE_URL` canlı adres olmalı.
- [ ] Kurslarım sayfasındaki kurs kartları ve ilerleme örnek veride (Favorilerim ve Değerlendirmelerim gerçek veriden).
- [ ] Bülten e-postasının alt bilgisindeki "Aboneliği düzenle" ve "Abonelikten çık" bağlantıları gerçek gönderimle denenmedi (yalnız önizlemede görüldü). Stüdyo → Bültenler'de bir taslaktan test adresine (`EMAIL_TEST_TO`) test e-postası gönder; e-posta istemcisinde iki bağlantının da açıldığını (tıklama izleme yönlendirmesiyle `/newsletter/manage/<anahtar>/` sayfasına gittiğini) ve Gmail'in tek tıkla abonelikten çıkma düğmesinin göründüğünü kontrol et.

## Yorumlar
- [ ] Onay bekleyen yorum gelince yöneticiye bildirim (e-posta servisi bağlanınca).
- [ ] Kullanıcıya yorumu onaylandığında / gizlendiğinde bilgi (isteğe bağlı).

## Diğer
- [ ] `django-admin-sortable2` Django 6.1 desteği ekleyince projedeki uyumluluk dosyalarını sil: `templates/adminsortable2/edit_inline/*-django-6.1.html`, `static_files/adminsortable2/js/actions-6.1.js`.
- [ ] `django-admin-honeypot-updated-2021` bakımsız; Django yükseltmesinde sorun çıkarsa kendi sahte giriş sayfamızı yaz.
- [ ] Prod'da statik dosyalar için `ManifestStaticFilesStorage`.
- [ ] Prod alan adı: `hakanyalcinkaya.com` (ayarlar hazır, `config/settings/settings_prod.py`). Nginx: `www.hakanyalcinkaya.com` → `https://hakanyalcinkaya.com` 301 yönlendirmesi, `X-Forwarded-Proto` başlığı, SSL sertifikası (www dahil). Sunucuda uzun ve rastgele `SECRET_KEY`, `DEBUG=False`. HSTS 1 saatle başlıyor; sorunsuzsa `SECURE_HSTS_SECONDS=31536000`.
- [ ] Bunny panelinde izinli alan adları: `hakanyalcinkaya.com` (canlı) ve `local.hakanyalcinkaya.com` (geliştirme); Vimeo izinli alan adları ayarda (`VIMEO_EMBED_DOMAINS`).
- [ ] SendGrid: SMTP bağlandı (`MAILERS`, `.env` `SENDGRID_API_KEY`). Kalan: gönderici alan adının SendGrid'de doğrulanması (SPF/DKIM), gerçek gönderim testi, sipariş e-postaları.
- [ ] Google Analytics. KVKK gereği analitik çerez izin alınmadan yüklenemez: çerez izin bandı (Kabul et / Reddet, kategori seçimi) ve Çerez Politikası güncellemesi birlikte yapılmalı.
- [ ] Bülten servisi ve İYS kaydı.
- [ ] Yasal metinlerin (Gizlilik, Kullanım Şartları, Çerez) hukuki incelemesi.
