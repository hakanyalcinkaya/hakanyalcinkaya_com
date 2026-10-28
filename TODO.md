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
- [ ] CDN token koruması: imzalı oynatma adreslerinin biçimini Bunny'nin gerçek CDN'inde doğrula, sonra `.env`'de `BUNNY_CDN_TOKEN_AUTH=True` yap (kod hazır, `course/bunny.py` `_signed`). Bunny panelinde MediaCage DRM kapalı, izinli alan adları dolu olmalı.
- [ ] İzlenen süreyi her 5 saniyede bir veritabanına yaz (kaldığı yerden devam; `LessonProgress.position_seconds`); ders sayfasında ilerleme ve "tamamlandı" işaretleri şu an boş.
- [ ] Kurs sayfasının tanıtım metinleri (neler öğreneceksin, kimler için ...) aynı slug'lı örnek kurstan geliyor; kurs maddeleri (CourseHighlight) doldurulunca örnek veri kaldırılabilir. Ana sayfa, kurs listesi, sepet ve kütüphane hâlâ örnek veride.
- [ ] Ders/tanıtım videosu değiştirilince eski video Bunny'de kalıyor; istenirse yeni video hazır olunca eskisini silme seçeneği.
- [ ] Prod: Celery işçisini servis olarak çalıştır (systemd/supervisor), Redis'i ayrı veritabanı numarasıyla kullan; sunucuda büyük dosya yüklemesi için Nginx `client_max_body_size` ve zaman aşımı ayarları.

## Diğer
- [ ] `django-admin-sortable2` Django 6.1 desteği ekleyince projedeki uyumluluk dosyalarını sil: `templates/adminsortable2/edit_inline/*-django-6.1.html`, `static_files/adminsortable2/js/actions-6.1.js`.
- [ ] `django-admin-honeypot-updated-2021` bakımsız; Django yükseltmesinde sorun çıkarsa kendi sahte giriş sayfamızı yaz.
- [ ] Prod'da statik dosyalar için `ManifestStaticFilesStorage`.
- [ ] SendGrid entegrasyonu (şifre sıfırlama, sipariş e-postaları; şifre sıfırlama şu an geliştirmede terminale yazılıyor).
- [ ] Google Analytics. KVKK gereği analitik çerez izin alınmadan yüklenemez: çerez izin bandı (Kabul et / Reddet, kategori seçimi) ve Çerez Politikası güncellemesi birlikte yapılmalı.
- [ ] Bülten servisi ve İYS kaydı.
- [ ] Yasal metinlerin (Gizlilik, Kullanım Şartları, Çerez) hukuki incelemesi.
