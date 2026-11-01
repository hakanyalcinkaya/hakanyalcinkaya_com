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
- Açılma: takvime göre (kayıttan sonraki her gün bir paket) ve önceki paketi bitiren beklemeden sonrakini açabilir. Bu davranışlar akış kurallarıyla yönetilir (ör. 30 gün giriş yapmayanın programı durur, mail gider). Durdurulan programın nasıl devam edeceğini (giriş yapınca, maildeki düğmeyle, satın almayla) akış belirler.
- Ücretli teklifler: aynı kursun tamamı (beklemeden açma), diğer mevcut kurslar, yeni premium kurs.
- Varsayım (onaylanacak): ücretsiz izleyen kursu satın alınca tüm içerik açılır, "satın almayanlar" akışından çıkıp "satın alanlar" akışına geçer.

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
- Ödül ve teklif mailleri (bonus, indirim, sertifika, kurs önerisi) ayrı gider, kendi günlük sınırı olur.
- Kişi iki türü hesap ayarlarında ayrı ayrı kapatır. Teklif mailleri ticari ileti sayılır: onay ve İYS gerekir; hukukçuyla teyit edilmeli.

### Ölçüm

- Test süresiz; Stüdyo'da "Test hunisi": kayıt → ilk gün → 7. gün → 30. gün → teklife tıklama → satın alma.
- Akış raporu: gönderildi, açıldı, tıklandı (`EmailLog`), 7 gün içinde izlemeye dönen, kullanılan kod, satın alma; kontrol grubuyla karşılaştırma.
- Kayıt kaynağı UTM ile; ilk geliş kaynağı sunucu tarafında, çerezsiz saklanır.

## Teknik taslak (mevcut koda göre)

- `learning.EnrollmentSource`'a `FREE` (ücretsiz kayıt). Erişim kontrolü (`page/views.py` `_enrolled`, `Enrollment.objects.has_access`) kayda bakıyor; ücretsiz kayıtta ek olarak ders kilidi gerekir.
- `Course`: ücretsiz program açık/kapalı, günlük ders sayısı. `Lesson`: "ilk gün açık", bonus ders işareti.
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

## Açık sorular

- Satın alma sonrası akış geçişi varsayımının onayı.
- Ödül ve teklif maillerinin günlük sınırı (öneri: 1).
- Kurs başına günlük ders sayıları ve hangi derslerin ilk gün açık olacağı.
- İlk akış seti: her kurs için satın alanlar ve satın almayanlar akışlarının tetikleyici/gün listesi.
