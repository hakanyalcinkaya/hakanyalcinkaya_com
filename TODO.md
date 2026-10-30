# TODO

Sonraya bırakılan işler, yayın önceliğine göre. Tamamlananı listeden çıkar.

## 1. Eski müşterilerin kursa erişmesi (en acil)
- [ ] Ders videolarını yükle: Python'da 109 dersin hiçbirinde, React'te 336 dersin 307'sinde, Django'da 327 dersin 306'sında video yok (30 Ekim 2026, yerel veritabanı). Davet e-postasından önce Stüdyo'dan Bunny'ye yüklenmeli.
- [ ] Podia davetleri: aktarım yerelde yapıldı (171 sipariş), davet gönderilmedi. `PODIA_MIGRATE.md` 7–10. adımlar: `send_podia_invites --dry-run`, kendine gönderim, `.env`'den `EMAIL_REDIRECT_TO` kaldırma (`SITE_URL` canlı adres), parça parça gönderim. Prod'da aktarım durumu kontrol edilmeli; geçiş bitene kadar Podia'daki yeni satışlar için `import_podia` yeniden çalıştırılır. Şifre bağlantısı `PASSWORD_RESET_TIMEOUT` kadar geçerli (varsayılan 3 gün); süresi geçen "Şifremi unuttum" kullanır.
- [ ] SendGrid: gönderici alan adını SendGrid'de doğrula (SPF/DKIM), gerçek gönderimle dene. Doğrulama olmadan davetler spam'e düşebilir.
- [ ] Cloudflare'de `hakanyalcinkaya.com` ve `www` kayıtları "DNS only" (gri bulut) olmalı: proxy açıkken yükleme 100 MB / 100 sn ile sınırlı, stüdyoda büyük video yüklenemez. Sonra 100 MB'tan büyük bir videoyla dene.
- [ ] Bunny CDN token koruması: panelde (Stream → kütüphane → Security) "Token Authentication" açılınca imzalı adresi gerçek CDN'de doğrula, sonra `.env`'de `BUNNY_CDN_TOKEN_AUTH=True` (kod hazır, `course/bunny.py` `_signed`). İkisi birlikte yapılmalı; yoksa videolar oynamaz.
- [ ] Bunny panelinde izinli alan adları: `hakanyalcinkaya.com` (canlı) ve `local.hakanyalcinkaya.com` (geliştirme); Vimeo izinli alan adları ayarda (`VIMEO_EMBED_DOMAINS`, varsayılanda hâlâ `hakanyalcinkaya.dev` var).
- [ ] Gerçek videoda deneme: 5 sn sonra tamamlandı, oynatıcı tercihleri (hız/kalite/altyazı otomatik kayıt, tam ekran; iPhone Safari'de tam ekran desteklenmeyebilir).

## 2. İçerik temizliği (yayından önce)
- [ ] Örnek veriyi kaldır: kurs sayfası tanıtım metnini aynı slug'lı örnek kurstan birleştiriyor (`page/content.py` `course_card` ve kurs detayı, `catalog.course_by_slug`); sepette oturumdaki örnek kurs yolu (`page/catalog.py` `cart_add`, `page/content.py` sepet) ve yayında kurs yokken gösterilen örnek kurslar. Gerçek kursların madde listeleri (CourseHighlight) dolu.
- [ ] Yasal metinlerde eski alan adı: Gizlilik ve Kullanım Şartları "hakanyalcinkaya.dev" diyor (`page/catalog.py`); `hakanyalcinkaya.com` olmalı. Yasal metinlerin hukuki incelemesi.
- [ ] Sitede görünen `[PLACEHOLDER]` metinleri: giriş/kayıt sayfaları altı (`templates/page/account/auth_base.html`), şifre sıfırlama gönderildi (`password_reset_sent.html`), hesap ayarlarında e-posta değişikliği (`settings.html`), teşekkürler sayfasında sipariş no ve e-posta bildirimi (`thanks.html`, `order.number` var), yasal sayfalar (`legal.html`; `page/catalog.py`'de iletişim e-postası ×2, iade politikası).
- [ ] Kurs fiyatları yer tutucu (₺100 / ₺100 / ₺99,79): gerçek fiyatlar girilmeli.
- [ ] Django ve Python kurslarının erişim notu "platformdan izlemeye başlayabilirsin" diyor; sadeleştir (Stüdyo → Kurs bilgileri → Erişim notu).
- [ ] Ders adlarındaki yazım hataları ("Kulllanımı", "Klasorlerin", ...).
- [ ] Sayfa sayfa son kontrol (masaüstü, 375 px mobil, açık/koyu tema). Yapıldı: ana sayfa, kurs listesi, kurs sayfası. Kalan: önizleme dersi, kursun tüm yorumları, `/reviews/`, üst menü/alt bilgi/tema paneli, 404, sepete ekle/çıkar, sepet, hemen al, ödeme, teşekkürler, giriş, kayıt, şifre sıfırlama akışı (geçerli ve süresi dolmuş bağlantı), hesap ayarları, çıkış, Kurslarım, ders sayfası, oynatıcı tercihleri, yorum yazma, kursu olmayan üyenin ders sayfası.

## 3. Satış
- [ ] iyzico kartla ödeme (TL, KDV dahil): ödeme sayfası hazır, kart seçeneği "Yakında" (`page/views.py` `CARD_PAYMENT_OPEN = False`). Bağlanınca `Order.create_from_cart(cart, email, user, provider="card")` ile bekleyen sipariş, iyzico onayında `Order.mark_paid`, başarısızlıkta `mark_failed`. Anahtarlar `.env`'de (`IYZICO_API_KEY`, `IYZICO_SECRET_KEY`), önce sandbox.
- [ ] Misafir siparişi (`page/views.py` `checkout`): misafir yalnız e-posta yazar (doğrulanmaz); o e-postayla hesap varsa sipariş o hesaba bağlanır (`content.checkout_buyer`). Hesap yoksa sipariş kullanıcısız açılır: iyzico onayından sonra teşekkür sayfasında ad soyad sorulup hesap açılmalı (şifre belirleme e-postasıyla), `order.user` atanıp kurs kayıtları açılmalı (`Order.mark_paid` kullanıcısız siparişte kayıt açmaz).
- [ ] İşlem e-postaları: şablonlar hazır (`templates/emails/`, önizleme: Stüdyo → E-postalar), koddan yalnız şifre sıfırlama, bülten onayı, bülten ve Podia daveti gönderiliyor. Bağlanacaklar: hoş geldin (kayıt), satın alma onayı (havale/EFT ile Stüdyo'dan onaylanan sipariş dahil), ödeme başarısız, iade, kurs bitirme, yorum onayı, şifre ve e-posta değişikliği, yöneticiye yeni sipariş ve onay bekleyen yorum bildirimi.
- [ ] Bağlantıyla gelen indirim kodu: `?code=KOD` oturumda beklet, sepet oluşunca uygula; kurs ve paket sayfalarında "KOD uygulandı" ile indirimli fiyatı göster.
- [ ] Sepeti boşaltan kullanıcılara ileride indirim bildirimi gönder (boşaltılan sepetler silinmeden `emptied` durumunda tutuluyor).

### Paketler (Bundle)
- [ ] `/bundles/` liste ve `/bundles/<slug>/` detay sayfalarının tasarımı (kurs sayfasının düzeninden türetilebilir).
- [ ] Kurs sayfasının alt kısmında "Bu kurs şu paketlerde de var" bölümü.
- [ ] Sepette paket ve paketin içindeki tek kurs birlikteyse tek kursu sepetten çıkar, bildirim göster.
- [ ] Kullanıcı paketteki bir kursa zaten sahipse paket fiyatından o kurs için ödediği tutarı düş (hediye/manuel ise 0 düşülür, fiyat 0'ın altına inmez).

## 4. Öğrenci araçları
- [ ] Kaldığı saniyeden devam: `LessonProgress.record_position()` hazır ama hiçbir yerden çağrılmıyor. Oynatıcı her 5 saniyede bir yazmalı, ders kaldığı saniyeden açılmalı.
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
- [ ] Ders/tanıtım videosu değiştirilince eski video Bunny'de kalıyor; istenirse yeni video hazır olunca eskisini silme seçeneği.
- [ ] `django-admin-sortable2` Django 6.1 desteği ekleyince projedeki uyumluluk dosyalarını sil: `templates/adminsortable2/edit_inline/*-django-6.1.html`, `static_files/adminsortable2/js/actions-6.1.js`.
- [ ] `django-admin-honeypot-updated-2021` bakımsız; Django yükseltmesinde sorun çıkarsa kendi sahte giriş sayfamızı yaz.
