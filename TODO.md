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
- [ ] İzlenen süreyi her 5 saniyede bir veritabanına yaz ve dersi kaldığı saniyeden aç (`LessonProgress.position_seconds`). "Tamamlandı" işareti, kenar listesi ve ilerleme çubuğu artık gerçek veriden geliyor.
- [ ] Kurs sayfasının tanıtım metinleri (neler öğreneceksin, kimler için ...) aynı slug'lı örnek kurstan geliyor; kurs maddeleri (CourseHighlight) doldurulunca örnek veri kaldırılabilir. Ana sayfa, kurs listesi, sepet ve kütüphane hâlâ örnek veride.
- [ ] Ders/tanıtım videosu değiştirilince eski video Bunny'de kalıyor; istenirse yeni video hazır olunca eskisini silme seçeneği.
- [ ] Studio'da "Orijinali indir": Bunny'de "Keep original files" açık kalmalı; indirme, CDN token koruması açılınca kısa süreli imzalı bağlantıyla yapılır (doğrudan dosya erişimi şu an 403).
- [ ] Vimeo videolarını da kendi oynatıcımızla (HLS) oynatma seçeneği: Standard planda API HLS bağlantısı veriyor; bağlantılar süreli, sayfa açılışında alınıp kısa süre önbellekte tutulmalı.
- [ ] Gerçek videoda deneme: 5 sn sonra tamamlandı, oynatıcı tercihleri (hız/kalite/altyazı otomatik kayıt, tam ekran; iPhone Safari'de tam ekran desteklenmeyebilir). Yerelde `http://local.hakanyalcinkaya.com/` (80 portu) üzerinden.
- [ ] Prod: Celery işçisini servis olarak çalıştır (systemd/supervisor), Redis'i ayrı veritabanı numarasıyla kullan; sunucuda büyük dosya yüklemesi için Nginx `client_max_body_size` ve zaman aşımı ayarları.

## Öğrenci araçları (giriş yapmış ve kursu satın almış kullanıcı)
- [ ] Video notu: oynatıcıda "Not ekle" düğmesi; not videonun o anki saniyesine kaydedilir. Oynatıcının ilerleme çubuğunda notların yerinde işaret (mark) görünür; işarete tıklanınca o saniyeye gidilir. `learning.Note` modeline saniye alanı (ör. `position_seconds`) eklenecek.
- [ ] Derslerde not alma şu an kapalı (Studio → Ayarlar); açılmadan önce not kaydetme bağlanmalı (ders sayfasındaki alan örnek, `learning.Note` kullanılmıyor).
- [ ] Kurs erişimi gerçek satın almaya bağlanmalı: `owns_course` şu an örnek (oturumdaki satın alma + örnek kütüphane). `learning.Enrollment` modeli var ama sipariş/ödeme akışına bağlı değil; favoriler, tamamlama, değerlendirme ve ders kilitleri bu kurala dayanıyor.
- [ ] Kurslarım sayfasındaki kurs kartları ve ilerleme örnek veride (Favorilerim ve Değerlendirmelerim gerçek veriden).

## Yorumlar
- [ ] Onay bekleyen yorum gelince yöneticiye bildirim (e-posta servisi bağlanınca).
- [ ] Kullanıcıya yorumu onaylandığında / gizlendiğinde bilgi (isteğe bağlı).

## Diğer
- [ ] `django-admin-sortable2` Django 6.1 desteği ekleyince projedeki uyumluluk dosyalarını sil: `templates/adminsortable2/edit_inline/*-django-6.1.html`, `static_files/adminsortable2/js/actions-6.1.js`.
- [ ] `django-admin-honeypot-updated-2021` bakımsız; Django yükseltmesinde sorun çıkarsa kendi sahte giriş sayfamızı yaz.
- [ ] Prod'da statik dosyalar için `ManifestStaticFilesStorage`.
- [ ] SendGrid entegrasyonu (şifre sıfırlama, sipariş e-postaları; şifre sıfırlama şu an geliştirmede terminale yazılıyor).
- [ ] Google Analytics. KVKK gereği analitik çerez izin alınmadan yüklenemez: çerez izin bandı (Kabul et / Reddet, kategori seçimi) ve Çerez Politikası güncellemesi birlikte yapılmalı.
- [ ] Bülten servisi ve İYS kaydı.
- [ ] Yasal metinlerin (Gizlilik, Kullanım Şartları, Çerez) hukuki incelemesi.
