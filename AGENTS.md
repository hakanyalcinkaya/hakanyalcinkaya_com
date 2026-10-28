# Global geliştirme kuralları — Django + HTMX

Tüm projelerde geçerli varsayılanlar (Claude Code, Codex, Cursor). **Projenin kendi `AGENTS.md` / `CLAUDE.md` / `.cursor/rules` dosyaları bu dosyadan önce gelir**; çelişkide proje kazanır.

## İletişim
- Yanıtlar Türkçe; gerektiğinde netleştirici soru sor. Kod, tanımlayıcı ve commit mesajı İngilizce olabilir.
- Yanıtta önce sonuç, sonra gerekçe. Doğrulamadığın şeyi doğrulanmış gibi yazma.

## Güvenlik sınırları
- **Migration:** `makemigrations` / `migrate` çalıştırma, `migrations/` altına dosya yazma. Model değişince hangi app için `makemigrations <app>` gerektiğini ve beklenen şemayı bildir. `makemigrations --check --dry-run` serbest.
- **Git:** istenmedikçe commit yok; push hiçbir zaman. Commit'e agent/araç imzası (`Co-Authored-By` vb.) eklenmez.
- Gizli bilgi koda yazılmaz (`.env`); veri silen/üzerine yazan komut öncesi hedefe bak ve sor.

## Başlamadan
- Projenin talimat dosyalarını oku; değiştireceğin app'te **en benzer mevcut özelliği** bul ve kalıp al. Var olan helper/dekoratör/mixin'i yeniden yazma, hayali ad üretme.
- Kodu çevresindeki dosya gibi yaz: adlandırma, yorum yoğunluğu, import düzeni.

## Django mimarisi — uygun katmanda iş mantığı, ince view
- Nesneye ait kurallar modelde; görünürlük ve filtreler QuerySet'te; girdi doğrulaması Form'da; çok modelli orkestrasyon gerektiğinde service katmanında olmalı. Basit CRUD için service zorunlu değil.
- İş kuralı, durum geçişi, hesaplama, link üretimi **modelde**: instance metodu / `@property` (`is_*`, `can_*`, `has_*`), fiil metotları (`approve()`), `QuerySet` metotları (`published()`, `visible_to(user)`) + `as_manager()`.
- View sırası: yetki → nesneyi (yetki kapsamlı queryset'ten, `get_object_or_404`) yükle → form / model metodu → `messages` → render / redirect. View'da `status ==` zinciri, tarih hesabı yok.
- Girdi doğrulama ve girdiden kayıt üretimi formda (`ModelForm`, crispy-forms).
- Çok modelli ağır hesap app içinde ayrı modülde; uzun iş Celery görevinde (argüman olarak id, `transaction.on_commit`).
- Projenin mevcut FBV/CBV tercihine uy; büyük app'te `views/` paketi kullanabilirsin.
- Context `dict(...)`; döngü değişkeni `_` olmaz (`gettext as _` ile çakışır).

## URL ve linkler
- Path küçük harf + **tire** (`region-league/<slug:slug>/`), `name=` **snake_case** (`league_detail`), her app `app_name` + kökte `namespace`.
- Kanonik nesne URL'si için `get_absolute_url()`, nesneye doğal eylemler için `get_*_url()`; genel, filtreli veya kullanıcıya bağlı endpoint için `{% url %}` / `reverse()` / helper kullan. Her URL'yi modele taşıma.
- `i18n_patterns` kararını mevcut proje URL yapısına göre ver. HTMX isteği tek başına dil önekini kaldırmayı gerektirmez.

## HTMX
- Aynı view, aynı URL: `request.htmx` → partial, değilse tam sayfa; tam sayfa partial'ı `{% include %}` eder.
- Filtre durumu GET parametresinde, anında (`hx-get`, `hx-trigger` gecikmeli, `hx-push-url`/`hx-replace-url`, `hx-sync="this:replace"`).
- Veri değiştiren istek POST/DELETE + gerekiyorsa `hx-confirm`. HTMX'e düz `redirect` yerine `HttpResponseClientRedirect`.
- CSRF ve HTMX kütüphanesi base şablonda (`<body hx-headers='{"X-CSRFToken": "{{ csrf_token }}"}'>`); sayfalarda tekrarlama.
- Partial'lar `templates/<app>/partials/_ad.html`; hedef id'leri sabit ve anlamlı.

## Sorgular
- Şablon döngüsündeki FK → `select_related`, ters FK/M2M → `prefetch_related`/`Prefetch`; `__str__` ve şablonda çağrılan metotların eriştiği ilişkiler dahil.
- Sayım/toplam `annotate`/`aggregate`; sayfalı listede `order_by` benzersiz alanla biter.

## Çeviri ve zaman
- Kullanıcıya görünen her metin `_()` / `{% translate %}`; modellerde `gettext_lazy`, view'da `gettext`; `ugettext` yok.
- `USE_TZ`, `TIME_ZONE` ve iş takviminin yerel tarih tanımına uy; `timezone.localdate()` yalnız aware datetime ile uygun yapılandırmada kullanılır. `date.today()` sunucu timezone'una bağımlıdır.

## Doğrulama ve rapor
- `python manage.py check`; tam sayfa ve `HTTP_HX_REQUEST="true"` isteğini test et. CSRF'i ayrıca `Client(enforce_csrf_checks=True)` ile doğrula; sorgu sayısını ölç.
- Refactor davranış değiştirmez: durum kodu, izinler, yönlendirme, mesaj, önemli HTML/partial sözleşmesini kıyasla. Tam HTML diff yardımcıdır, byte-byte eşitlik zorunlu değildir.
- Raporda: değişen dosyalar (yol:satır), doğrulama komutu + sonucu, doğrulanamayanlar, kullanıcının yapacağı migration/çeviri adımı.

## Skiller
`django-feature`, `django-fat-model`, `django-urls-links`, `django-htmx-view`, `django-htmx-components`, `django-review`, `django-testing`, `django-security`, `django-performance`, `django-architecture`. Yalnız ilgili skill'leri yükle.
