# Ücretsiz program ve akışlar (plan)

Uzilla'dan önce hakanyalcinkaya.com'da denenecek model: kurslara ücretsiz kayıt, günlük açılan program, otomatik akışlar (hatırlatma, bonus, indirim) ve ücretliye geçişin ölçülmesi. Bu dosya planlama aşamasında alınan kararları toplar; kod henüz yazılmadı (1 Kasım 2026).

## Amaç

- Ücretsiz kayıt olanların ne kadarının başladığını, programa devam ettiğini ve ücretliye geçtiğini ölçmek.
- Hangi akışın (hatırlatma, bonus, indirim) dönüşümü gerçekten artırdığını kontrol grubuyla görmek.
- Bu test Uzilla'nın yalnız öğrenci tarafını ölçer. Eğitmenlerin bu modele para verip vermeyeceği ayrıca (görüşme, ön satış) öğrenilmeli.

## Kararlar

### Ücretsiz program

- Üç kurs birden başlar; videolar prod'da hazır.
- Program kurs başına açılır/kapanır. Sonradan yayınlanan kurslarda (premium dahil) isteğe göre açılır ya da kapatılır.
- Program kapatılınca ücretsiz kayıtlı kişi o güne kadar açılan içeriği korur, yeni içerik açılmaz. Yeni ücretsiz kayıt alınmaz.
- İlk gün: Stüdyo'da ders başına "ilk gün açık" işareti. İşaretli derslerin hepsi kayıttan hemen sonra açılır.
- Sonraki günler: her gün sabit sayıda ders açılır; sayı kurs başına ayarlanır.
- Açılma: **günlük tavan.** Her gün en fazla N ders açılır; N kurs başına ayarlanır, varsayılan 1. O günün derslerini bitirmek ek ders açmaz. Takvime göre biriken günler izlenebilir. Ücretli "tümünü aç" tavanı kaldırır; "hızlandırma" ödülü o gün +X ders açar. Program durdurma ve devam kuralları akışlarda (ör. 30 gün izlemeyenin programı durur, mail gider; devam yolu akışta seçilir).
- **Freemium sınırı (kurs başına, isteğe bağlı).** Kursun ücretsiz kısmı sınırlanabilir: ör. 200 dersin ilk 100'ü ya da belirli bir bölüme kadar. Sınırdan sonrası günlük tavandan bağımsız olarak kilitli; devam için satın alma gerekir. Sınır yoksa kursun tamamı günlük tavanla ücretsiz. Öneri: Stüdyo'da bölüm (section) düzeyinde "ücretsiz kısmın sonu" işareti; ders sayısıyla sınır bölüm ortasında keser. Alternatif: kurs ayarında "ücretsiz ders sayısı".
- Ücretli teklifler: aynı kursun tamamı (freemium sınırını ve günlük tavanı kaldırır), diğer mevcut kurslar, yeni premium kurs.
- Ücretsiz izleyen kursu satın alınca tüm içerik açılır, "satın almayanlar" akışından çıkıp "satın alanlar" akışına geçer (onaylandı). Mevcut kurs kaydı `purchase`'a yükseltilir, yeni kayıt açılmaz.
- Program uzunluğu ve günlük ders sayısı kursa göre belirlenir; "30 gün" yalnız örnek, akış ve stratejiye göre değişir.

### Akışlar

- Akış = tetikleyici + eşik + aksiyon. Örnekler: 3 gün izlemedi → hatırlatma; %20 tamamladı → bonus ders; %50 tamamladı → indirim kodu; 30 gün giriş yok → programı durdur ve mail at; 7 gün üst üste zamanında → hızlandırma.
- İki ayrı akış kitlesi: kursu satın alanlar, satın almadan izleyenler.
- Akış kursa göre hazırlanır; başka kursa kopyalanıp uyarlanır (kısa kursta bonus ve indirim daha erken güne çekilebilir).
- Ödüller: kişiye bağlı tek kullanımlık süreli indirim kodu, bonus ders (kursta normalde gizli, o kişiye açılır), programı hızlandırma (sonraki günler beklemeden açılır), sertifika.
- Kontrol grubu akış başına ayarlanır (%; 0 = kapalı). Koşula uyanların bu kadarına aksiyon uygulanmaz, yalnız kaydedilir; akışın gerçek etkisi iki grubun farkıyla ölçülür.
- Geriye dönük çalışma: akışlar o anki duruma bakar, yeni akış eski kayıtlara da uygulanabilir. Aktifleştirmeden önce önizleme ("şu an 142 kişiye uyuyor" ve örnek liste); eskilere uygulanıp uygulanmayacağı her seferinde seçilir. Toplu gönderim saatlik sınırla yayılır.
- Aynı akış aynı kayda bir kez çalışır. İzlememe gibi tekrarlayan koşullarda kişi araya izleme girdiyse yeniden çalışabilir, en fazla tekrar sayısıyla. İlerleme eşiklerinde istenirse üst sınır (ör. yalnız %20–%40 arası).

### Mail

- Program mailleri (yeni gün açıldı, hatırlatma, program durduruldu): kişi başı günde en fazla 1; çakışırsa önceliği yüksek olan gider, diğeri ertesi güne kalır.
- Ödül ve teklif mailleri (bonus, indirim, sertifika, kurs önerisi) ayrı gider; kişi başı günde en fazla 1.
- Kişi iki türü hesap ayarlarında ayrı ayrı kapatır. Teklif mailleri ticari ileti sayılır: onay ve İYS gerekir; hukukçuyla teyit edilmeli.

### Ölçüm

- Test süresiz; Stüdyo'da "Test hunisi": kayıt → ilk gün → 7. gün → 30. gün → teklife tıklama → satın alma.
- Akış raporu: gönderildi, açıldı, tıklandı (`EmailLog`), 7 gün içinde izlemeye dönen, kullanılan kod, satın alma; kontrol grubuyla karşılaştırma.
- Kayıt kaynağı UTM ile; ilk geliş kaynağı sunucu tarafında, çerezsiz saklanır.

## Teknik taslak (mevcut koda göre)

- `learning.EnrollmentSource`'a `FREE` (ücretsiz kayıt). Erişim kontrolü (`page/views.py` `_enrolled`, `Enrollment.objects.has_access`) kayda bakıyor; ücretsiz kayıtta ek olarak ders kilidi gerekir.
- `Course`: ücretsiz program açık/kapalı, günlük tavan (varsayılan 1). `Section`: "ücretsiz kısmın sonu" işareti (freemium sınırı). `Lesson`: "ilk gün açık", bonus ders işareti.
- Kilit kontrolü iki katman: freemium sınırı (satın alma gerekir) ve günlük tavan (bekleme gerekir). Kilitli ders sayfası ikisini ayrı anlatır: "yarın açılıyor" / "devamı için kursu aç".
- İlerleme yüzdesi ücretsiz kullanıcıda ücretsiz kısma göre mi, kursun tamamına göre mi hesaplanacak? F3/F4 eşikleri için ücretsiz kısma göre (sınır varsa).
- Model metotları: `Course.enroll_free(user)`, `Enrollment.program_day()`, `Enrollment.unlocked_lessons()`, `Enrollment.is_on_schedule()`, `Lesson.is_unlocked_for(enrollment)`. Kilitli ders: "yarın açılıyor" sayfası ve ücretli teklif.
- Program durumu kayıtta: durduruldu mu, ne zaman, hızlandırma ile açılan ek gün sayısı, bonus erişimleri.
- Kayıt akışı: kurs sayfasında POST `course/<slug>/enroll/`; misafir kayıt sayfasına (`?next`), kayıttan sonra kurs kaydı açılır ve ilk güne gider.
- Yeni app (`automation`): `Flow` (kurs, kitle, tetikleyici, eşik, aksiyon, mail metni, ödül ayarı, kontrol grubu %, öncelik, tekrar sınırı, durum, kopyala), `FlowRun` (akış, kayıt, zaman, kontrol grubunda mı, mail, indirim kodu).
- Koşullar `EnrollmentQuerySet` metotları: `inactive_for(days)`, `progress_at_least(percent)` (`with_progress()` üzerinden), `enrolled_before(days)`, `without_purchase()`, `not_logged_in_for(days)`.
- Kişiye bağlı indirim kodu: `discount.Discount`'a `user` alanı; `max_uses=1`, `valid_until`, kurs hedefi.
- Çalıştırıcı: `run_flows` yönetim komutu + saatlik görev. Projede Celery beat ayarı yok: `django-celery-beat` ya da sunucuda cron.
- Mailler `templates/emails/` ve `mailing` ile; mail tercihleri (program / teklif) hesap ayarlarında.
- UTM: ilk geliş oturumda tutulur, kayıtta kullanıcıya yazılır.
- Migration gerekecek app'ler: `learning`, `course`, `discount`, `account`, yeni `automation`.

## Önkoşullar

- SendGrid'de gönderici alan adı doğrulaması (SPF/DKIM); yoksa hatırlatmalar spam'e düşer.
- Ticari ileti onayı ve İYS kaydı (teklif mailleri için).
- Trafik planı: YouTube, Udemy öğrencileri, bülten, sosyal medya; bağlantılarda UTM.

## Ayrı notlar

- Sertifika: genel sisteme eklenecek; ücretli alanlar ve ücretsiz izleyenler için iki tür. Taslak: ad, kurs, tarih, benzersiz numara içeren PDF ve numarayla herkese açık doğrulama sayfası.
- 171 eski (Podia) müşterinin tam erişimi var; bilgilendirme maili ayrı iş.

## İlk akış seti (taslak)

Günler kurs uzunluğuna göre ölçeklenir: `G` = kursun program uzunluğu (gün). Kurs başına kopyalanıp uyarlanır. "İzlemedi" = o kursta `last_watched_at` (hiç izlemediyse kayıt tarihi) üzerinden. Kontrol grubu yalnız mail/ödül akışlarında; durdurma akışlarında yok.

### Satın almadan izleyenler

| # | Tetikleyici | Aksiyon | Tür | Kontrol |
|---|---|---|---|---|
| F1 | Kayıt oldu, 24 saat içinde ilk dersi açmadı | "İlk dersin seni bekliyor" | program | %10 |
| F2 | 3 gün izlemedi (en fazla 3 kez, arada izleme olursa yeniden) | Hatırlatma, kaldığı ders bağlantısı | program | %10 |
| F3 | İlerleme ≥ %25 | Bonus ders açılır + mail | ödül | %10 |
| F4 | İlerleme ≥ %50 | Kişiye bağlı indirim kodu (7 gün geçerli): tümünü aç / diğer kurs / premium | teklif | %10 |
| F5 | 7 gün üst üste günün paketini aynı gün bitirdi | Hızlandırma: o gün +1 paket | ödül | 0 |
| F6 | Kayıttan `G/2` gün geçti, satın almadı, ilerleme < %25 | Premium kurs tanıtımı / ön satış | teklif | %10 |
| F7 | 30 gün izlemedi | Programı durdur + "devam etmek için giriş yap" maili; giriş yapınca kaldığı yerden devam | program | 0 |
| F8 | Ücretsiz kısmı bitirdi (sınır varsa) | Tebrik + sertifika (ücretsiz türü) + diğer kurs teklifi | ödül | 0 |
| F9 | Freemium sınırına ulaştı | "Devamı için kursu aç" teklifi + 3 gün sonra indirim kodu | teklif | %10 |
| F10 | Sınıra ulaştıktan 14 gün sonra satın almadı | Son hatırlatma, kodun bitiş tarihi | teklif | %10 |

### Satın alanlar

| # | Tetikleyici | Aksiyon | Tür | Kontrol |
|---|---|---|---|---|
| P1 | Satın aldı, 3 gün içinde hiç izlemedi | "Kursuna başla" | program | 0 |
| P2 | 7 gün izlemedi (en fazla 3 kez) | Hatırlatma | program | %10 |
| P3 | İlerleme ≥ %50 | Bonus ders | ödül | 0 |
| P4 | Kursu bitirdi | Tebrik + sertifika (ücretli türü) + yorum isteği | ödül | 0 |
| P5 | Bitirdikten 7 gün sonra | Diğer kurs / premium için indirim kodu | teklif | %10 |

Öncelik (aynı gün çakışırsa): F7 > F1 > F2; teklif maillerinde F9 > F4 > F10 > F6.

## İnceleme bulguları (1 Kasım 2026)

Karar bekleyenler:

- ~~Kilit modeli~~ Karar: günlük tavan, kurs başına, varsayılan 1 (yukarıda).
- **Ücretli ürün.** Sitede şu an satılan ürün yok (100 ₺ fiyat yalnız test için). Freemium sınırı olan kurslarda "kursun kalanını aç" gerçek bir teklif; sınırsız kurslarda yalnız premium kalır. Kurs başına gerçek fiyat belirlenmeli. Premium kurs (ör. AI ajanlarıyla kod yazmak) ön satış sayfası testten önce hazır olmalı; bu aynı zamanda premium talebini kodsuz ölçer.
- **Karar noktası.** Test süresiz; yine de 90. günde yazılı eşiklerle değerlendirme tarihi.
- **Günlük "yeni gün açıldı" maili** gönderilsin mi? Öneri: yalnız izlemeyene hatırlatma ya da haftalık özet; her gün mail yorgunluk yaratır.
- Ücretsiz kayıtlı kullanıcı yorum yazabilsin mi? (Şu an `has_access` izin verir.) En azından yorumda kaynak saklanmalı.

Eksik önkoşullar:

- Kartla ödeme kapalı (`page/views.py` `CARD_PAYMENT_OPEN = False`); iyzico bağlanmadan dönüşüm ölçülmez.
- İşlem mailleri (hoş geldin, satın alma onayı) bağlı değil.
- Ücretsiz kayıt formunda işaretsiz ticari ileti onay kutusu + İYS.
- Ücretsiz hizmet için kısa kullanım şartları; gizlilik politikasına UTM ve akış kayıtları; hesap silme planına `FlowRun` ve UTM.
- Kurs schema `offers` fiyatı ücretsiz olunca güncellenmeli.

Kodla çakışan noktalar:

- `page/content.py` `owned_course_ids`: her kayıt "sahip" sayılır; ücretsiz kayıtlı "Eğitimlerinde" görür, satın alamaz. Kaynak ayrımı gerekir.
- `order/models.py` `mark_paid`: `get_or_create` ücretsiz kaydı `free` bırakır, siparişi bağlamaz; mevcut kayıt yükseltilmeli.
- Ders kilidi tek noktada değil: ders sayfası, `autoplay_next`, `continue_lesson`, Önceki/Sonraki ile tamamlandı işareti, müfredat listesi.
- `LessonProgress.completed_at` Önceki/Sonraki ile işaretlenir; ilerleme tetikleyicileri tıklayarak kazanılabilir. İzleme konumu (`record_position`) ya da süre şartı gerekir.
- Paket fiyat düşümü (TODO 3) ücretsiz kaydı da düşer; kaynak ayrımı.
- Bonus dersler müfredat toplamından ve ilerleme yüzdesinden hariç tutulmalı.
- "30 gün giriş yapmadı": `last_login` oturum boyunca güncellenmez; `last_watched_at` ya da son istek zamanı.
- "Gün" tanımı: Europe/Istanbul takvim günü, mail saati (ör. 09:00) belirlenmeli.
- Site içi olay kaydı (`Event`: kullanıcı, olay, zaman) yok; "teklife tıklama" hunisi için gerekir.
- Kontrol grubu %10 küçük kitlede anlamsız; birkaç yüz kayıt birikmeden okunmaz.

Kapsam ve sıra (öneri):

- Aşama 0: premium ön satış sayfası, iyzico, SendGrid doğrulaması, onay kutusu/İYS, işlem mailleri.
- Aşama 1: ücretsiz kayıt, günlük kilit, kaynak ayrımı (owned, mark_paid, bundle), kodda sabit ilk akış seti, `run_flows`, `FlowRun`, basit kontrol grubu, Stüdyo'da huni ve akış sayıları.
- Aşama 2 (veri gelirse): Stüdyo akış kurucu, kopyalama, önizleme, bonus ders yönetimi, sertifika.
- Paralel: 5–10 eğitmenle Uzilla görüşmesi; ücretsiz program yalnız öğrenci tarafını ölçer.

Araç kararı: Aşama 1 kendi kodla (`mailing` altyapısı hazır). Görsel akış kurucu gerekirse Customer.io (EU veri merkezi) referans; KVKK yurt dışı aktarım yükümlülüğü var. Açık kaynak alternatif: Dittofeed, Mautic. SendGrid otomasyonları davranış tetikleyicisi için yetersiz.

## Açık sorular

- Freemium sınırı bölüm işaretiyle mi, ders sayısıyla mı?
- Kurs başına: freemium sınırı var mı ve nerede, günlük tavan (varsayılan 1), gerçek fiyat, bundan çıkan program uzunluğu ve ilk gün açık dersler (kursa göre, birlikte belirlenecek).
- İlk akış setinin gün ve yüzde değerleri (taslak yukarıda, birlikte gözden geçirilecek).
