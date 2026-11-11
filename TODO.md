# TODO

Sonraya bırakılan işler, yayın önceliğine göre. Tamamlananı listeden çıkar.

## 1. Eski müşterilerin kursa erişmesi (en acil)
- [ ] Ders videolarını yükle: Python'da 109 dersin hiçbirinde, React'te 336 dersin 307'sinde, Django'da 327 dersin 306'sında video yok (30 Ekim 2026, yerel veritabanı). Davet e-postasından önce Stüdyo'dan Bunny'ye yüklenmeli.
- [ ] Podia davetleri: aktarım yerelde yapıldı (171 sipariş), davet gönderilmedi. `PODIA_MIGRATE.md` 7–10. adımlar: `send_podia_invites --dry-run`, kendine gönderim, `.env`'den `EMAIL_REDIRECT_TO` kaldırma (`SITE_URL` canlı adres), parça parça gönderim. Prod'da aktarım durumu kontrol edilmeli; geçiş bitene kadar Podia'daki yeni satışlar için `import_podia` yeniden çalıştırılır. Davetteki şifre bağlantısı 3 gün geçerli (`account.tokens.INVITE_TIMEOUT`; Şifremi unuttum 1 saat); süresi geçen "Şifremi unuttum" kullanır.
- [ ] SendGrid: alan adı doğrulandı, gerçek gönderim denendi (31 Ekim 2026 destek yanıtı: SPF, DKIM `s1` ve DMARC `pass`, gelen kutusuna düştü). Kalan:
  - ~~Prod'da `EMAIL_REDIRECT_TO`~~ Kaldırıldı (2 Kasım 2026, `.env`'de yorum satırı; uWSGI ve Celery yeniden başlatıldı): davet denemesi doğrudan `hakan.yalcin.kaya@gmail.com`'a gitti. Müşterilere artık gerçek e-posta gidiyor; `send_podia_invites` `--email`/`--limit` olmadan 157 kişinin hepsine gönderir.
  - ~~SendGrid Click/Open Tracking~~ Kodda kapatıldı (2 Kasım 2026): her e-postaya `X-SMTPAPI` başlığı (`mailing/backends.py` `SENDGRID_NO_TRACKING`), panel ayarı ne olursa olsun bu sitenin e-postalarında SendGrid takibi yok; açılma/tıklama sitenin kendi takibinde (`/e/o/`, `/e/c/`, `EmailLog`). Prod'da doğrulandı (2 Kasım 2026, Podia daveti): bütün bağlantılar `hakanyalcinkaya.com/e/c/`, tek açılma pikseli; SPF, DKIM `s1`, DMARC `pass`.
  - DMARC `p=NONE`; birkaç hafta sorunsuz gönderimden sonra `p=quarantine` ve `rua=` rapor adresi.
  - ~~Sunucu hostname'i~~ Çözüldü ve prod'da doğrulandı (1 Kasım 2026): `EMAIL_HOSTNAME` ile `Message-ID: ...@hakanyalcinkaya.com`, `Received: from hakanyalcinkaya.com`. Sunucu geneli için tarafsız bir FQDN (`srv1...`) isteğe bağlı; diğer projelere yarar.
- [ ] Cloudflare'de `hakanyalcinkaya.com` ve `www` kayıtları "DNS only" (gri bulut) olmalı: proxy açıkken yükleme 100 MB / 100 sn ile sınırlı, stüdyoda büyük video yüklenemez. Sonra 100 MB'tan büyük bir videoyla dene.
- [ ] Bunny CDN token koruması: panelde (Stream → kütüphane → Security) "Token Authentication" açılınca imzalı adresi gerçek CDN'de doğrula, sonra `.env`'de `BUNNY_CDN_TOKEN_AUTH=True` (kod hazır, `course/bunny.py` `_signed`). İkisi birlikte yapılmalı; yoksa videolar oynamaz.
- [ ] Bunny panelinde izinli alan adları: `hakanyalcinkaya.com` (canlı) ve `local.hakanyalcinkaya.com` (geliştirme); Vimeo izinli alan adları ayarda (`VIMEO_EMBED_DOMAINS`, varsayılanda hâlâ `hakanyalcinkaya.dev` var).
- [ ] Gerçek videoda deneme (Bunny ve Vimeo): 5 sn sonra tamamlandı, kaldığı saniyeden devam (yerelde yalnız HLS test videosuyla denendi), oynatıcı tercihleri (hız/kalite/altyazı otomatik kayıt, tam ekran; iPhone Safari'de tam ekran desteklenmeyebilir).

## 2. İçerik temizliği (yayından önce)
- [ ] Örnek veriyi kaldır: kurs sayfası tanıtım metnini aynı slug'lı örnek kurstan birleştiriyor (`page/content.py` `course_card` ve kurs detayı, `catalog.course_by_slug`); sepette oturumdaki örnek kurs yolu (`page/catalog.py` `cart_add`, `page/content.py` sepet) ve yayında kurs yokken gösterilen örnek kurslar. Gerçek kursların madde listeleri (CourseHighlight) dolu.
- [ ] Django ve Python kurslarının erişim notu "platformdan izlemeye başlayabilirsin" diyor; sadeleştir (Stüdyo → Kurs bilgileri → Erişim notu).
- [ ] Ders adlarındaki yazım hataları ("Kulllanımı", "Klasorlerin", ...).
- [ ] Sayfa sayfa son kontrol (masaüstü, 375 px mobil, açık/koyu tema). Yapıldı: ana sayfa, kurs listesi, kurs sayfası, önizleme dersi, kursun tüm yorumları, `/reviews/`, üst menü/alt bilgi/tema paneli, sepete ekle/çıkar, sepet, hemen al, ödeme, teşekkürler (`/thanks/<sipariş no>/`). Kalan: 404, giriş, kayıt, şifre sıfırlama akışı (geçerli ve süresi dolmuş bağlantı), hesap ayarları, çıkış, Kurslarım, ders sayfası, oynatıcı tercihleri, yorum yazma, kursu olmayan üyenin ders sayfası.

## 3. Satış
- [ ] iyzico kartla ödeme (Checkout Form, TRY, KDV dahil; PayTR 11 Kasım 2026'da kaldırıldı): kod bağlandı, gerçek kartla uçtan uca deneme yapılmadı. Canlıya geçiş: prod `.env`'de `IYZICO_API_KEY`, `IYZICO_SECRET_KEY`, `IYZICO_BASE_URL=https://api.iyzipay.com` ve `CARD_PAYMENT_OPEN=all` (önce `staff` ile küçük tutarlı gerçek ödeme denenip iade edilmeli; deneme için stüdyoda düşük fiyatlı bir kurs **Taslak** olarak açılabilir: taslak kurs yalnız yöneticilere listelenir, sepete eklenir ve satın alınabilir), sonra site yeniden yüklenir; eski `PAYTR_*` satırları silinebilir. iyzico panelinde (Ayarlar › Bildirimler) webhook adresi `https://hakanyalcinkaya.com/checkout/iyzico/webhook/` tanımlanmalı (müşteri dönüşten önce sayfayı kapatırsa ya da ödeme incelemeye düşerse siparişi o öder). Taksit açılacaksa `IYZICO_MAX_INSTALLMENT` (2, 3, 6, 9, 12) ve Mesafeli Satış Sözleşmesi'ndeki "tek seferde" ifadesi değişmeli. Akış: ödeme formu ad soyad ve telefonu alır (iyzico'ya gider, saklanmaz; TC kimlik no yer tutucu, fatura adresi sabit metin) → `content.create_card_order` + `start_card_payment` → `/checkout/pay/<sipariş no>/` iyzico'nun ödeme sayfasına yönlenir → iyzico tarayıcıyı `/checkout/iyzico/callback/<sipariş no>/` adresine token ile POST eder → `content.apply_card_payment` token ile sonucu iyzico'dan sorar, `Order.apply_card_result` ile öder → `?result=ok` sayfası onay gelene kadar HTMX ile sorar. İstemci `order/iyzico.py`.
- [ ] Ödeme sağlayıcısı başvurusu için sayfalar hazır (1 Kasım 2026): Hakkımda (`/about/`), Teslimat ve İade Şartları, Mesafeli Satış Sözleşmesi, Gizlilik Politikası, footer'da ödeme logoları. Ödeme sayfasında zorunlu sözleşme onay kutusu var (`CheckoutForm.agreement`, misafir ve üye). Kalan: onayın zamanı siparişte saklanmalı (`Order`'a ör. `agreement_accepted_at`, `makemigrations order` gerekir). Satın alma onayı e-postasında sözleşme bağlantısı var.
- [ ] E-posta değişikliği onaysız: hesap ayarlarında yeni adres doğrudan kaydediliyor (`page/forms.py` `EmailChangeForm.save`). Yeni adrese onay bağlantısı gönderilip tıklanınca değişmeli (`emails/email_change` şablonu hazır).
- [ ] Hesap silme (KVKK m.11/1-e, m.7): kullanıcı silme isteyebilir, en geç 30 gün içinde ücretsiz yanıt verilmeli (m.13). Gizlilik Politikası bu hakkı ve "hesabını kapattığında silinir ya da anonimleştirilir" sözünü veriyor (`page/catalog.py` "Saklama süresi", "Hakların") ama sitede kapatma yolu yok.
  - Hesap ayarlarına (`page/views.py` `account_settings`) "Hesabımı sil" bölümü: şifreyle onay (form `page/forms.py`'de), POST, uyarı metni (kurslara erişim biter, geri alınamaz), sonra çıkış ve bilgi mesajı. Yanlış silmeye karşı isteğe bağlı e-postayla onay bağlantısı.
  - Silme mantığı modelde (ör. `User.delete_account()`), tek `transaction.atomic` içinde. `User` satırı silinmez, anonimleştirilir: e-posta `deleted-<uuid>@...`, ad soyad boş, `set_unusable_password()`, `is_active=False`. Böylece `SET_NULL` ilişkiler kopmaz, aynı e-postayla yeniden kayıt açılabilir.
  - Silinecekler (`CASCADE` olanlar, kullanıcı silinmediği için elle): `learning` Enrollment, LessonProgress, notlar, favoriler, oynatıcı tercihi; `cart` sepetleri; bülten aboneliği (`newsletter.Subscriber`, e-postaya göre); `InstructorProfile` varsa dokunma, eğitmen hesabı silinemesin.
  - Saklanacaklar (VUK 5 yıl, TTK 10 yıl, mesafeli satış kayıtları): `order.Order` ve OrderItem; `Order.email` kalır (fatura/sözleşme kaydı), yalnız `user` bağı kopar. Süre dolunca anonimleştirme ya da silme için periyodik imha komutu (Silme/Yok Etme Yönetmeliği: en geç 6 ayda bir).
  - Karar verilecekler: kurs yorumları (`course` Review, `SET_NULL`) silinsin mi yoksa "Silinmiş üye" adıyla kalsın mı; destek talepleri (`support.Ticket`/TicketMessage) ve e-posta kayıtları (`mailing` gönderim kaydı, `to_email` alanında adres var) ne kadar saklanacak.
  - Gizlilik Politikası'nı güncelle: hesap ayarlarından silme yolu, e-postayla başvuru (`SUPPORT_EMAIL`), 30 günlük yanıt süresi, yasal olarak saklanan kayıtlar ve süreleri. Saklama sürelerini muhasebeciyle teyit et.
  - Hesap silme onayı e-postası (`templates/emails/` altında yeni şablon) ve testler: silinen hesap giriş yapamaz, siparişler duruyor, aynı e-postayla yeniden kayıt çalışıyor.
- [ ] Misafir siparişi (`page/views.py` `checkout`): misafir yalnız e-posta yazar (doğrulanmaz). "Kartla öde"ye basınca o e-postayla hesap varsa sipariş ona bağlanır, yoksa şifresiz hesap açılır (`content.checkout_buyer`; ödeme tamamlanmasa da hesap kalır, misafir oturum açmış sayılmaz). Ödeme onayında `mark_paid` kurs kayıtlarını açar, satın alma onayı e-postası şifresiz hesaba "Şifreni belirle" bağlantısıyla gider. Kalan: ödeme onayından sonra teşekkür sayfasında ad soyad (bilgi tamamlama) adımı (ödeme formunda yazılan ad soyad şimdilik yalnız iyzico'ya gidiyor, hesaba yazılmıyor); şifresiz hesap teşekkür sayfasında oturumdaki sipariş numarasıyla görür.
- [ ] İşlem e-postaları: şablonlar hazır (`templates/emails/`, önizleme: Stüdyo → E-postalar), koddan şifre sıfırlama, bülten onayı, bülten, Podia daveti ve satın alma onayı (`Order.mark_paid` → `order.tasks.send_purchase_confirmation`) gönderiliyor. Bağlanacaklar: hoş geldin (kayıt), ödeme başarısız, iade, kurs bitirme, yorum onayı, şifre ve e-posta değişikliği, yöneticiye yeni sipariş ve onay bekleyen yorum bildirimi.
- [ ] Bağlantıyla gelen indirim kodu: `?code=KOD` oturumda beklet, sepet oluşunca uygula; kurs ve paket sayfalarında "KOD uygulandı" ile indirimli fiyatı göster.
- [ ] Sepeti boşaltan kullanıcılara ileride indirim bildirimi gönder (boşaltılan sepetler silinmeden `emptied` durumunda tutuluyor).

### Paketler (Bundle)
- [ ] `/bundles/` liste ve `/bundles/<slug>/` detay sayfalarının tasarımı (kurs sayfasının düzeninden türetilebilir).
- [ ] Kurs sayfasının alt kısmında "Bu kurs şu paketlerde de var" bölümü.
- [ ] Sepette paket ve paketin içindeki tek kurs birlikteyse tek kursu sepetten çıkar, bildirim göster.
- [ ] Kullanıcı paketteki bir kursa zaten sahipse paket fiyatından o kurs için ödediği tutarı düş (hediye/manuel ise 0 düşülür, fiyat 0'ın altına inmez).

## 4. Öğrenci araçları
- [ ] Video notu: oynatıcıda "Not ekle" düğmesi; not videonun o anki saniyesine kaydedilir. İlerleme çubuğunda notların yerinde işaret (mark), işarete tıklanınca o saniyeye gidilir. `learning.Note` modeline saniye alanı (`position_seconds`) eklenecek. Derslerde not alma şu an kapalı (Stüdyo → Ayarlar); açılmadan önce bağlanmalı.
- [ ] Udemy eğitmen yanıtları (karar bekliyor): ayrı gösterilecekse `Review.reply` alanı, `import_reviews`'un yanıtı `udemy-*-yorumlar.md` dosyalarından bu alana yazması, sitede ve stüdyoda gösterim. `makemigrations course` gerekir.
- [ ] Kullanıcıya yorumu onaylandığında / gizlendiğinde bilgi (isteğe bağlı).

## 5. Prod ve altyapı
- [ ] Prod'da paylaşılan önbellek (Redis): Vimeo HLS bağlantıları önbellekte (`course/vimeo.py` `playback`), şu an bellek içi önbellek.
- [ ] Prod'da statik dosyalar için `ManifestStaticFilesStorage`; sonra statik önbellek süresi 365 gün.
- [ ] HSTS 1 saatle başlıyor; birkaç gün sorunsuzsa `.env`'de `SECURE_HSTS_SECONDS=31536000`. SSL sertifikası (Sectigo DV) 15 Mayıs 2027'de bitiyor; yenileme adımları `_server/README.md`.
- [ ] Bülten e-postasının alt bilgisindeki "Aboneliği düzenle" ve "Abonelikten çık" bağlantıları gerçek gönderimle denenmedi. Stüdyo → Bültenler'de bir taslaktan test adresine (`EMAIL_TEST_TO`) gönder; iki bağlantının da `/newsletter/manage/<anahtar>/` sayfasına gittiğini ve Gmail'in tek tıkla abonelikten çıkma düğmesinin göründüğünü kontrol et.
- [ ] Yayından sonra kurs sayfalarını Google Rich Results Test'ten, paylaşım önizlemesini Facebook Sharing Debugger'dan geçir. Django ve Python kurslarında `courseWorkload` ders süreleri dolunca kendiliğinden gelir.

## 6. Daha sonra
- [ ] Site geneli schema: ana sayfaya `Person` (`sameAs` ile sosyal hesaplar) ve `WebSite`, görünen breadcrumb'lar için `BreadcrumbList`. İsteğe bağlı `/llms.txt`.
- [ ] Google Analytics. KVKK gereği analitik çerez izin alınmadan yüklenemez: çerez izin bandı (Kabul et / Reddet, kategori seçimi) ve Çerez Politikası güncellemesi birlikte yapılmalı.
- [ ] Bülten servisi ve İYS kaydı.
- [ ] `django-admin-sortable2` Django 6.1 desteği ekleyince projedeki uyumluluk dosyalarını sil: `templates/adminsortable2/edit_inline/*-django-6.1.html`, `static_files/adminsortable2/js/actions-6.1.js`.
- [ ] `django-admin-honeypot-updated-2021` bakımsız; Django yükseltmesinde sorun çıkarsa kendi sahte giriş sayfamızı yaz.
