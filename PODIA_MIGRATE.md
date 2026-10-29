# Podia'dan taşınma

Podia'da eğitim satın almış kişilerin hesaplarını ve kurs erişimlerini bu siteye aktarıp onlara "Hesabın taşındı"
e-postası gönderme adımları. Sıra önemli: **önce aktar, kontrol et, en son e-posta gönder.**

Aktarım (`import_podia`) hiç e-posta göndermez. E-postaları yalnız `send_podia_invites` gönderir.

Komutlar proje klasöründe, sanal ortam açıkken çalıştırılır (yerelde `python` = `/Users/hy/.pyenv/versions/hy_env/bin/python`;
sunucuda aynı komutlar sunucudaki ortamla).

---

## 1. Podia dosyasını indir

Podia → Sales → Invoices → dışa aktar (xlsx). Dosyada şu sütunlar olmalı:
`Invoice #, Date, Name, Email, Status, Items, Subtotal, Discount, Total, Currency, Coupon`.

Yalnız `Status = Completed` satırlar aktarılır; diğerleri raporda "tamamlanmamış" olarak sayılır.

## 2. Kursları hazırla

Her Podia ürünü sitede bir kursla eşleşmeli. Eşleşme, ürün adında geçen bir metin ile kursun **slug**'ı arasında kurulur.

| Podia ürün adında geçen | Kurs slug'ı (şu an) |
|---|---|
| `React 18.x` | `react` |
| `Python ve Django` | `django` |
| `İki Eğitmen` | `python` |

- Slug'ları Django admin → Kurslar'dan kontrol et. Slug değişirse aşağıdaki komutlarda `--map` değerlerini de değiştir.
- Kursun bölümlerini ve derslerini Stüdyo'dan yükle.

## 3. Aktarımı dene (hiçbir şey kaydetmez)

```bash
python manage.py import_podia /yol/podia-invoices.xlsx \
  --map "React 18.x=react" --map "Python ve Django=django" --map "İki Eğitmen=python" --dry-run
```

Rapordaki satırlara bak:

- **Sipariş / Kullanıcı / Kurs kaydı**: kaç yeni, kaç zaten var.
- **Eşleşmeyen ürün**: kırmızı satır varsa o ürün için bir `--map` ekle ya da kursu aç; sonra denemeyi tekrarla.
- **Hata satırları** (tarih okunamadı, e-posta boş): Podia dosyasında düzelt ya da not al.

## 4. Aktarımı yap

Aynı komut, `--dry-run` olmadan:

```bash
python manage.py import_podia /yol/podia-invoices.xlsx \
  --map "React 18.x=react" --map "Python ve Django=django" --map "İki Eğitmen=python"
```

- Kullanıcılar şifresiz açılır (şifreyi davet e-postasındaki bağlantıyla kendileri belirler).
- Her fatura bir sipariş, her kurs bir kurs kaydı (`Eski platformdan aktarıldı`) olur.
- **Tekrar çalıştırmak güvenli**: daha önce aktarılan faturalar atlanır. Podia'dan yeni dosya indirip aynı komutla yalnız
  yenileri ekleyebilirsin.

## 5. Kontrol et

- **Django admin → Siparişler**: ödeme sağlayıcısı `podia` olan siparişler, tutarlar (EUR) ve kalemler.
- **Django admin → Kurs kayıtları**: kaynak "Eski platformdan aktarıldı"; kurs başına sayılar beklenenle uyuşuyor mu.
- **Birkaç müşteriyi elle kontrol et**: aynı kişinin birden fazla kursu varsa hepsi görünüyor mu.
- **E-postanın önizlemesi**: Stüdyo → E-postalar → "Hesabın taşındı" → sağdaki kutuya bir müşterinin e-postasını yaz.
  Ad, aktarılan kurslar ve tutarlar o kişinin gerçek verisiyle görünür.

## 6. Kursları yayınla

Stüdyo'dan kursu, bölümlerini ve derslerini **yayında** yap. Yayında olmayan kursa alıcılar ulaşamaz; davet komutu da
yayında olmayan aktarılmış kurs varken göndermez.

Kontrol (giriş yapmadan ya da müşteri olmayan bir hesapla):

- Ana sayfa ve kurs listesinde kurslar görünüyor.
- Kurs sayfasında önizleme dersleri açık, diğerleri kilitli.

## 7. Davetleri dene

```bash
python manage.py send_podia_invites --dry-run
```

Hiçbir şey göndermez. Gösterir:

- Kaç kişiye gideceğini ve ilk 20 adresi.
- Yayında olmayan aktarılmış kurs varsa uyarı (`Yayında değil: ...`).
- `EMAIL_REDIRECT_TO` duruyorsa "Test modu" uyarısı.

## 8. Kendine gönder

Aktarılanlar arasında kendi adresin varsa:

```bash
python manage.py send_podia_invites --email hakan.yalcin.kaya@gmail.com
```

E-postayı kontrol et:

- Ad, kurs listesi ve tutarlar doğru mu.
- "Şifreni belirle" bağlantısı açılıyor mu; şifre belirleyince giriş yapılıyor mu.
- Giriş sonrası **Eğitimlerim**'de kurs görünüyor, dersler açılıyor mu.
- Kurs kartında "Eğitime git" yazıyor, sepete eklenemiyor mu.

Gönderilen her e-posta Stüdyo → E-postalar → **Gönderim günlüğü**'nde görünür (şifre bağlantısı kayıtta gizli).

## 9. Gerçek gönderim için ayarları değiştir

`.env`:

```bash
# Kaldır: bu satır durdukça bütün e-postalar sana gider
EMAIL_REDIRECT_TO=...

# Ekle: Stüdyo'daki "Test gönder" düğmeleri yine sana gitsin
EMAIL_TEST_TO=hakanyalcinkaya@gmail.com
```

Ardından **sunucuyu ve Celery işçisini yeniden başlat** (ayarlar yeniden başlatınca okunur).

`send_podia_invites --dry-run` çıktısında artık "Test modu" uyarısı olmamalı.

## 10. Davetleri parça parça gönder

```bash
python manage.py send_podia_invites --limit 20
```

- Gönderim günlüğünden hata olup olmadığına, birkaç e-postanın açıldığına bak.
- Sorun yoksa kalanların hepsine:

```bash
python manage.py send_podia_invites
```

Komutun kuralları:

- Daveti almış kişiye **ikinci kez gönderilmez**; komutu istediğin kadar tekrar çalıştırabilirsin.
- Bir adreste gönderim hatası olursa diğerlerine devam eder; hatalı adresler bir sonraki çalıştırmada yeniden denenir.
- Birine yeniden göndermek gerekirse: `--email adres --resend`.
- Yayında olmayan kurs varken göndermek gerekirse (önerilmez): `--allow-unpublished`.

## 11. Sonrası

- **Şifre belirlemeyenler**: Şifre bağlantısı 3 gün geçerlidir (Django varsayılanı). Bağlantıyı kaybeden ya da süresi geçen kişi giriş sayfasındaki "Şifremi unuttum" ile yeni
  bağlantı alabilir (şifresi olmayan aktarılmış hesaplar için de çalışır).
- **Yeni Podia satışları**: Yeni dosyayla 3–5. adımları tekrarla, sonra `send_podia_invites` yalnız henüz davet
  almamış kişilere gönderir.
- **Takip**: Gönderim günlüğünde "Hesabın taşındı" şablonunun açılma ve tıklama oranları; Django admin → Kullanıcılar'da
  son giriş tarihleri.
- **Ödeme**: Sitede online ödeme şimdilik kapalı ("Ödeme yakında"); sepete ekleme açık.
