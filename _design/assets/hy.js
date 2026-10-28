/* hakanyalcinkaya.dev ortak betik
   1) Tema: ilk boyamadan önce koyu/açık tema ve vurgu rengini Bootstrap 5.3 değişkenlerine yazar.
   2) Veri: eğitimler, yorumlar, vurgu renkleri.
   3) Yardımcılar: dc bileşenlerinin ortak üst menü, tema paneli, mobil menü ve bülten formu değerleri.
   <head> içinde support.js ile birlikte, senkron yüklenmelidir; helmet içindeki betikler asenkron eklenir. */
(function () {
  'use strict';

  /* ---------- Tema ---------- */
  var ACC = { indigo: '#6366F1', blue: '#3B82F6', orange: '#F97316', pink: '#EC4899' };
  var ON = { indigo: '#ffffff', blue: '#ffffff', orange: '#0b0b0f', pink: '#0b0b0f' };
  var TH = {
    dark: { '--bs-body-bg': '#09090b', '--bs-body-bg-rgb': '9,9,11', '--bs-tertiary-bg': '#111113', '--bs-tertiary-bg-rgb': '17,17,19', '--bs-secondary-bg': '#1a1a1e', '--bs-secondary-bg-rgb': '26,26,30', '--bs-body-color': '#f4f4f5', '--bs-body-color-rgb': '244,244,245', '--bs-emphasis-color': '#ffffff', '--bs-emphasis-color-rgb': '255,255,255', '--bs-secondary-color': '#a1a1aa', '--bs-tertiary-color': '#8b8b94', '--bs-border-color': 'rgba(255,255,255,.14)', '--bs-border-color-translucent': 'rgba(255,255,255,.08)', '--bs-form-invalid-color': '#f87171', '--bs-form-invalid-border-color': '#f87171', '--bs-success': '#4ade80', '--bs-box-shadow': '0 24px 48px -28px rgba(0,0,0,.9)' },
    light: { '--bs-body-bg': '#ffffff', '--bs-body-bg-rgb': '255,255,255', '--bs-tertiary-bg': '#f7f7f9', '--bs-tertiary-bg-rgb': '247,247,249', '--bs-secondary-bg': '#eeeef2', '--bs-secondary-bg-rgb': '238,238,242', '--bs-body-color': '#0a0a0c', '--bs-body-color-rgb': '10,10,12', '--bs-emphasis-color': '#000000', '--bs-emphasis-color-rgb': '0,0,0', '--bs-secondary-color': '#4d4d56', '--bs-tertiary-color': '#62626b', '--bs-border-color': 'rgba(10,10,12,.16)', '--bs-border-color-translucent': 'rgba(10,10,12,.09)', '--bs-form-invalid-color': '#c81e1e', '--bs-form-invalid-border-color': '#c81e1e', '--bs-success': '#15803d', '--bs-box-shadow': '0 24px 48px -30px rgba(0,0,0,.22)' }
  };
  function rgb(h) { var n = parseInt(h.slice(1), 16); return [(n >> 16) & 255, (n >> 8) & 255, n & 255].join(','); }
  function read(k) { try { return localStorage.getItem(k); } catch (e) { return null; } }
  function get() { var t = read('site-theme'), a = read('site-accent'); return { theme: TH[t] ? t : 'dark', accent: ACC[a] ? a : 'indigo' }; }
  function apply(t, a, save) {
    if (!TH[t]) t = 'dark'; if (!ACC[a]) a = 'indigo';
    var r = document.documentElement, v = TH[t], hex = ACC[a], mix = t === 'dark' ? 'white' : 'black';
    var text = t === 'dark' ? 'color-mix(in oklab, ' + hex + ' 70%, white)' : 'color-mix(in oklab, ' + hex + ' 78%, black)';
    r.setAttribute('data-bs-theme', t); r.style.colorScheme = t;
    for (var k in v) r.style.setProperty(k, v[k]);
    r.style.setProperty('--bs-primary', hex);
    r.style.setProperty('--bs-primary-rgb', rgb(hex));
    r.style.setProperty('--bs-primary-text-emphasis', text);
    r.style.setProperty('--bs-primary-bg-subtle', 'color-mix(in oklab, ' + hex + ' 14%, transparent)');
    r.style.setProperty('--bs-primary-border-subtle', 'color-mix(in oklab, ' + hex + ' 45%, transparent)');
    r.style.setProperty('--bs-link-color', text);
    r.style.setProperty('--bs-link-hover-color', text);
    r.style.setProperty('--bs-focus-ring-color', 'color-mix(in oklab, ' + hex + ' 35%, transparent)');
    r.style.setProperty('--hy-accent-hover', 'color-mix(in oklab, ' + hex + ' 84%, ' + mix + ')');
    r.style.setProperty('--hy-accent-on', ON[a]);
    if (save) { try { localStorage.setItem('site-theme', t); localStorage.setItem('site-accent', a); } catch (e) {} }
    return { theme: t, accent: a };
  }
  window.hyTheme = { get: get, apply: apply, accents: ACC };
  var s0 = get(); apply(s0.theme, s0.accent, false);

  /* ---------- Veri ---------- */
  var SITE = 'https://www.hakanyalcinkaya.dev/';
  var IMG = 'https://www.hakanyalcinkaya.dev/content-assets/public/eyJhbGciOiJIUzI1NiJ9.';
  var COURSES = [
    { slug: 'sifirdan-projelerle-front-end-ve-react-18-x-ogren', title: 'Sıfırdan Projelerle Front-End ve React 18.x Öğren', topic: 'frontend',
      desc: 'Front-End temellerinden React 18.x’e; sıfırdan, projelerle ilerleyen kapsamlı eğitim.', tags: ['Front-End', 'React 18.x'],
      short: 'Front-End ve React 18.x', duration: '52+ saat', lessons: 335, price: '€99.90', offer: '353371',
      page: 'course.dc.html',
      img: IMG + 'eyJvYmplY3Rfa2V5IjoiMGV4dG95bjBiMWtpNXdlamF3ZGdzY3IzaG9hbCIsImRvbWFpbiI6Ind3dy5oYWthbnlhbGNpbmtheWEuZGV2In0.hvzdBBCysCN5gl0Iv8pEQnxrynKN5xKJrc39SmoTCHU' },
    { slug: 'sifirdan-uctan-uca-projelerle-python-ve-django-ogren', title: 'Sıfırdan Uçtan Uca Projelerle Python ve Django Öğren', topic: 'python',
      desc: 'Python ve Django ile sıfırdan başlayıp uçtan uca projeler geliştirdiğin eğitim.', tags: ['Python', 'Django'],
      short: 'Python ve Django', duration: '51+ saat', lessons: 327, price: '€99.90',
      img: IMG + 'eyJvYmplY3Rfa2V5IjoicHM0ejFxeHc2MzF6cmR6a25pY2NtbG9xcmJwOSIsImRvbWFpbiI6Ind3dy5oYWthbnlhbGNpbmtheWEuZGV2In0.OD4yTFhvbJ4kumJPX0sSs7XzRHnujd_gO3dxWIsah3A' },
    { slug: 'iki-egitmen-ile-sifirdan-python-ogren', title: 'İki Eğitmen ile Sıfırdan Python Öğren', topic: 'python',
      desc: 'İki eğitmenin anlatımıyla Python’a sıfırdan başlangıç.', tags: ['Python', 'Başlangıç'],
      short: 'Sıfırdan Python', duration: 'Süre: [eklenecek]', lessons: 109, price: '€99.90',
      img: IMG + 'eyJvYmplY3Rfa2V5IjoiNmV5c2dpaDNzMWlrbXg4MmZsaHh4dzZrazYzYSIsImRvbWFpbiI6Ind3dy5oYWthbnlhbGNpbmtheWEuZGV2In0.PbsKDzpNk5s9tIGUUwFkcXz-iH2iinBndkyjQgIDrR8' }
  ].map(function (c, i) {
    // Tasarım dosyalarında detay sayfası olan eğitim yerel sayfaya, diğerleri canlı siteye gider.
    c.url = c.page || (SITE + c.slug);
    // Tasarımda satın alma akışı yerel sayfalarda. Canlı karşılıkları: /<slug>/add-to-cart ve /<slug>/buy?offer_id=...
    c.cart = 'cart.dc.html?ekle=' + c.slug;
    c.buy = 'checkout.dc.html?kurs=' + c.slug;
    c.cartLive = SITE + c.slug + '/add-to-cart';
    c.buyLive = c.offer ? SITE + c.slug + '/buy?offer_id=' + c.offer : SITE + c.slug;
    c.amount = parseFloat(String(c.price).replace(/[^0-9.]/g, '')) || 0;
    c.cartLabel = c.title + ' — sepete ekle';
    c.alt = c.title + ' eğitiminin kapak görseli';
    c.imgLabel = c.title + ' — eğitimi incele';
    c.metaLine = [c.duration, c.lessons + ' ders'].join(' · ');
    c.hid = 'egitim-' + (i + 1);
    return c;
  });
  var REVIEWS = [
    ['Gülnisa', 'Hocamızın emeğine sağlık. Anlamadığım birçok şeyi çok iyi anladım. Kurs içeriği çok güzel hazırlanmış. Hocamız her şeyi detaylıca anlatıyor ve konunun daha iyi anlaşılması için çeşitli örnek projeler yapıyor. Başka dersleri sabırsızlıkla bekliyorum'],
    ['Ferdi S.', 'Hakan Hocam gerçekten muazzam bilgi ve tecrübeleri ile harika bir eğitim hazırlamış. Eğitimi aldığım için çok mutluyum ve herkese tavsiye ederim.\n\nEdit: Eğitimin yarısı bitti bile ve çok eğlenceli geçiyor :)'],
    ['Mustafa B.', 'Dersine girdiğim en iyi Öğretmensiniz ve her bir kelimenizde ki bilgi benim için çok önemli . Totalde 52 saat ama bunun arka planında ki emeği görebiliyorum.\n\nUmarım bu bilgileri doğru bir şekilde kullanır ve sizinle paylaşma fırsatı yakalarım. Teşekürler'],
    ['Umut K.', 'Hakan hoca alanında gerçekten bayağı iyidir. Her eğitimini zevk alarak izleyeceğinizi düşünüyorum. İyi çalışmalar herkese :)'],
    ['Onur I.', 'Hakan hocamın Patika.dev deki eğitimlerinden oldukça memnun kaldığım için ve konu anlatımını kendi anlama biçimime yakın bulduğum gördüm ve bu eğitimi de ondan almaya karar verdim'],
    ['Ahmet Fatih R.', 'Her eğitiminde bir şeyleri öğretirken öylesine değil gerçekten öğrensinler şeklinde yaklaşımıyla, bence mükemmel üslubuyla. Kesinlikle çok kaliteli ve çok iyi bir eğitmen. Sayın Hakan Yalçınkaya benim nazarımda Hakan Yalçınkaya ve diğerleri gibi iddialı bir cümlenin karşılığı. Umarım hayatta her şey gönlünce olsun sayın Hocam. Sevgiler :)']
  ].map(function (r) { return { name: r[0], text: r[1], initial: r[0].charAt(0) }; });
  var ACCENTS = [['indigo', 'Indigo', '#6366F1', '#fff'], ['blue', 'Blue', '#3B82F6', '#fff'], ['orange', 'Orange', '#F97316', '#0b0b0f'], ['pink', 'Pink', '#EC4899', '#0b0b0f']];
  var EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/;
  var totalLessons = COURSES.reduce(function (n, c) { return n + c.lessons; }, 0);

  /* ---------- Bileşen yardımcıları ---------- */
  function initState(extra) {
    var s = get();
    var base = { theme: s.theme, accent: s.accent, panelOpen: false, menuOpen: false,
      fName: '', fEmail: '', nameError: '', emailError: '', touched: false, pending: false };
    for (var k in extra) base[k] = extra[k];
    return base;
  }

  // Dışarı tıklayınca tema paneli ve hesap menüsü kapanır, Escape hepsini kapatır, geniş ekranda mobil menü kapanır.
  function mount(c) {
    c._hyDoc = function (e) {
      if (c.state.panelOpen && c.panelRef.current && !c.panelRef.current.contains(e.target)) c.setState({ panelOpen: false });
      if (c.state.userOpen && c.userRef && c.userRef.current && !c.userRef.current.contains(e.target)) c.setState({ userOpen: false });
    };
    c._hyKey = function (e) { if (e.key === 'Escape' && (c.state.panelOpen || c.state.menuOpen || c.state.userOpen)) c.setState({ panelOpen: false, menuOpen: false, userOpen: false }); };
    c._hyResize = function () { if (window.innerWidth >= 992 && c.state.menuOpen) c.setState({ menuOpen: false }); };
    document.addEventListener('mousedown', c._hyDoc);
    document.addEventListener('touchstart', c._hyDoc, { passive: true });
    document.addEventListener('keydown', c._hyKey);
    window.addEventListener('resize', c._hyResize);
  }
  function unmount(c) {
    document.removeEventListener('mousedown', c._hyDoc);
    document.removeEventListener('touchstart', c._hyDoc);
    document.removeEventListener('keydown', c._hyKey);
    window.removeEventListener('resize', c._hyResize);
  }

  // Bölüm takibi: menüdeki karşılığı olmayan bölüm aktif işareti temizler.
  function observeSections(c, selector, ids, key) {
    if (!('IntersectionObserver' in window)) return null;
    var tracked = {}; ids.forEach(function (id) { tracked[id] = true; });
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (en) {
        if (!en.isIntersecting) return;
        var patch = {}; patch[key || 'active'] = tracked[en.target.id] ? en.target.id : '';
        c.setState(patch);
      });
    }, { rootMargin: '-45% 0px -50% 0px' });
    document.querySelectorAll(selector).forEach(function (el) { io.observe(el); });
    return io;
  }

  // Üst menü, tema paneli ve mobil menü değerleri. nav: [[id, href, label]], active: id
  function chrome(c, nav, active) {
    var s = c.state;
    var setPrefs = function (t, a) { var r = apply(t, a, true); c.setState({ theme: r.theme, accent: r.accent }); };
    return {
      year: new Date().getFullYear(),
      navItems: nav.map(function (n) {
        var on = n[0] === active;
        return { href: n[1], label: n[2], current: on ? 'page' : undefined, cls: on ? 'active' : '',
          chev: on ? 'text-primary-emphasis' : 'text-body-tertiary',
          onClick: function () { var p = { menuOpen: false }; if (n[1].charAt(0) === '#') p.active = n[0]; c.setState(p); } };
      }),
      panelRef: c.panelRef, panelOpen: s.panelOpen,
      togglePanel: function () { c.setState({ panelOpen: !c.state.panelOpen }); },
      themeIcon: s.theme === 'dark' ? 'bi-moon-stars' : 'bi-sun',
      themeOpts: [['dark', 'Koyu', 'bi-moon-stars'], ['light', 'Açık', 'bi-sun']].map(function (o) {
        var on = s.theme === o[0];
        return { label: o[1], icon: o[2], checked: on ? 'true' : 'false', cls: on ? 'active' : 'text-body-secondary',
          onClick: function () { setPrefs(o[0], c.state.accent); } };
      }),
      swatches: ACCENTS.map(function (a) {
        var sel = s.accent === a[0];
        return { label: a[1] + (a[0] === 'indigo' ? ' (varsayılan)' : ''), hex: a[2], on: a[3],
          checked: sel ? 'true' : 'false', vis: sel ? 'visible' : 'hidden',
          ring: sel ? '0 0 0 2px var(--bs-body-bg), 0 0 0 4px ' + a[2] : 'none',
          onClick: function () { setPrefs(c.state.theme, a[0]); } };
      }),
      accentLabel: (ACCENTS.filter(function (a) { return a[0] === s.accent; })[0] || ACCENTS[0])[1],
      cartCount: cartGet().length, hasCart: cartGet().length > 0,
      menuOpen: s.menuOpen, menuCls: s.menuOpen ? 'show' : '', menuIcon: s.menuOpen ? 'bi-x-lg' : 'bi-list',
      menuLabel: s.menuOpen ? 'Menüyü kapat' : 'Menüyü aç',
      toggleMenu: function () { c.setState({ menuOpen: !c.state.menuOpen }); },
      closeMenu: function () { c.setState({ menuOpen: false }); }
    };
  }

  function validate(name, email) {
    return {
      nameError: name.trim().length < 2 ? 'Lütfen adını gir (en az 2 karakter).' : '',
      emailError: !email.trim() ? 'E-posta adresi gerekli.' : (!EMAIL_RE.test(email.trim()) ? 'Geçerli bir e-posta adresi gir.' : '')
    };
  }

  // Bülten formu değerleri. Sunucu bağlantısı yok; geçerli gönderimde bilgilendirme gösterilir.
  function newsletter(c) {
    var s = c.state;
    return {
      fName: s.fName, fEmail: s.fEmail, nameError: s.nameError, emailError: s.emailError, pending: s.pending,
      nameInvalid: s.nameError ? 'true' : 'false', emailInvalid: s.emailError ? 'true' : 'false',
      nameCls: s.nameError ? 'is-invalid' : '', emailCls: s.emailError ? 'is-invalid' : '',
      onName: function (e) { var v = e.target.value; c.setState(function (st) { var p = { fName: v, pending: false }; if (st.touched) p.nameError = validate(v, st.fEmail).nameError; return p; }); },
      onEmail: function (e) { var v = e.target.value; c.setState(function (st) { var p = { fEmail: v, pending: false }; if (st.touched) p.emailError = validate(st.fName, v).emailError; return p; }); },
      onSubmit: function (e) {
        e.preventDefault();
        var st = c.state, errs = validate(st.fName, st.fEmail), ok = !errs.nameError && !errs.emailError;
        c.setState({ nameError: errs.nameError, emailError: errs.emailError, touched: true, pending: ok });
        if (!ok) { var el = document.getElementById(errs.nameError ? 'bulten-isim' : 'bulten-eposta'); if (el) el.focus(); return; }
        // TODO (backend): Podia e-bülten formuna / kendi API endpoint'ine POST edilecek.
      }
    };
  }

  /* ---------- Ders verisi ve tarayıcı kaydı ---------- */
  // Müfredatı düz ders listesine çevirir. Ders kimliği canlı adresin son parçasındaki sayıdır.
  function lessons(detail) {
    var flat = [];
    detail.curriculum.forEach(function (sec, si) {
      sec[1].forEach(function (l, li) {
        var m = /\/(\d+)-[^\/]*$/.exec(l[1]);
        flat.push({ id: m ? m[1] : String(flat.length + 1), title: l[0], live: l[1], preview: !!l[2],
          si: si, li: li, n: flat.length + 1, section: sec[0] });
      });
    });
    return flat;
  }
  // Ders oynatıcı sayfası: kayıtlı öğrenci veya önizleme sürümü.
  function lessonHref(id, preview) { return 'lesson.dc.html?' + (preview ? 'erisim=onizleme&' : '') + 'ders=' + id; }
  // Yalnızca bu tarayıcıda tutulan kayıtlar (ilerleme, notlar). Gerçek hesapta sunucuya taşınacak.
  function load(key, fallback) { try { var v = localStorage.getItem(key); return v ? JSON.parse(v) : fallback; } catch (e) { return fallback; } }
  function save(key, value) { try { localStorage.setItem(key, JSON.stringify(value)); } catch (e) {} }

  /* ---------- Sepet (tasarımda tarayıcıda tutulur; canlıda sunucu sepeti) ---------- */
  var CART_KEY = 'hy-cart';
  function cartGet() { return load(CART_KEY, []).filter(function (s) { return COURSES.some(function (c) { return c.slug === s; }); }); }
  function cartSet(list) { save(CART_KEY, list); }
  function cartAdd(slug) { var l = cartGet(); if (l.indexOf(slug) < 0) l.push(slug); cartSet(l); return l; }
  function money(n) { return '€' + n.toFixed(2); }
  // Satın alma adımları: 0 Sepet, 1 Ödeme, 2 Tamamlandı. Geçilen adım onay işaretiyle gösterilir.
  function steps(active) {
    return ['Sepet', 'Ödeme', 'Tamamlandı'].map(function (label, i) {
      var done = i < active, on = i === active;
      return { label: label, num: String(i + 1), done: done, todo: !done, current: on ? 'step' : undefined, sep: i < 2,
        cls: on ? 'text-body' : done ? 'text-body-secondary' : 'text-body-tertiary',
        boxCls: on ? 'bg-primary' : done ? 'bg-primary-subtle text-primary-emphasis' : 'border text-body-tertiary',
        boxColor: on ? 'var(--hy-accent-on)' : 'inherit' };
    });
  }

  // Hesap bağlantıları. library tasarımda yerel Kurslarım sayfası; canlıda /p/products/library (doğrulandı).
  // settings doğrulanamadı; logout canlıda DELETE + CSRF ister, tasarımda yer tutucu.
  var ACCOUNT = {
    library: 'library.dc.html',
    settings: SITE + 'account/edit',
    logout: SITE + 'account/sessions',
    login: SITE + 'account/sessions/new',
    join: SITE + 'p/join'
  };

  // [PLACEHOLDER: oturumdaki kullanıcı] Canlıda hesap bilgisinden gelecek.
  var USER = { name: 'Öğrenci Adı', email: 'ogrenci@eposta.com', initial: 'Ö' };

  // Hesap menüsü değerleri. Giriş yapmış: kütüphane, katalog, ayarlar, çıkış. Giriş yapmamış: giriş, kayıt, katalog.
  // Bileşende userRef = React.createRef() ve userOpen durumu olmalı.
  function account(c, member) {
    var items = member
      ? [['Kurslarım', ACCOUNT.library, 'bi-collection-play'], ['Tüm Kurslar', 'courses.dc.html', 'bi-grid'],
         ['Ayarlar', ACCOUNT.settings, 'bi-gear'], ['Oturumu kapat', ACCOUNT.logout, 'bi-box-arrow-right', true]]
      : [['Giriş Yap', ACCOUNT.login, 'bi-box-arrow-in-right'], ['Kayıt Ol', ACCOUNT.join, 'bi-person-plus'],
         ['Tüm Kurslar', 'courses.dc.html', 'bi-grid', true]];
    return {
      account: ACCOUNT, user: USER, isMember: member, isGuest: !member,
      userMenu: items.map(function (m) { return { label: m[0], href: m[1], icon: m[2], divider: !!m[3] }; }),
      userOpen: !!c.state.userOpen, userRef: c.userRef,
      toggleUser: function () { c.setState({ userOpen: !c.state.userOpen, panelOpen: false }); }
    };
  }

  /* ---------- Yorum alanı: üçlü kayan kartlar (mobilde tekli), yüklenirken iskelet ---------- */
  var WIDE = '(min-width: 768px)';
  function reviewState() {
    return { revLoading: true, revPage: 0, revPaused: false, perView: window.matchMedia(WIDE).matches ? 3 : 1 };
  }
  // componentDidMount içinde çağrılır. Yorumlar canlıda API'den gelecek; tasarımda yükleme durumu kısa süre gösterilir.
  // Kendiliğinden ilerleme: üzerinde/odakta duraklar, azaltılmış hareket tercihinde ve sekme gizliyken çalışmaz.
  function mountReviews(c) {
    c._revLoad = setTimeout(function () { c.setState({ revLoading: false }); }, 900);
    c._revMq = window.matchMedia(WIDE);
    c._revMqFn = function (e) { c.setState({ perView: e.matches ? 3 : 1, revPage: 0 }); };
    c._revMq.addEventListener('change', c._revMqFn);
    var still = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    c._revTimer = setInterval(function () {
      var st = c.state;
      if (still || st.revLoading || st.revPaused || document.hidden) return;
      c.setState({ revPage: (st.revPage + 1) % Math.ceil(REVIEWS.length / st.perView) });
    }, 7000);
  }
  function unmountReviews(c) {
    clearTimeout(c._revLoad);
    clearInterval(c._revTimer);
    if (c._revMq) c._revMq.removeEventListener('change', c._revMqFn);
  }
  function reviews(c) {
    var s = c.state, pv = s.perView;
    var pages = Math.ceil(REVIEWS.length / pv), page = Math.min(s.revPage, pages - 1);
    var goPage = function (i) { c.setState({ revPage: (i + pages) % pages }); };
    var dots = [];
    for (var i = 0; i < pages; i++) (function (i) {
      dots.push({ label: (i + 1) + '. yorum sayfası', current: i === page ? 'true' : undefined,
        w: i === page ? '24px' : '8px', bg: i === page ? 'var(--bs-primary)' : 'var(--bs-border-color)', go: function () { goPage(i); } });
    })(i);
    return {
      reviewTotal: REVIEWS.length, revLoading: s.revLoading, revReady: !s.revLoading,
      revSkel: [0, 1, 2].map(function (i) { return { cls: i ? 'd-none d-md-block' : '' }; }),
      revX: (-page * 100) + '%', revPos: (page + 1) + ' / ' + pages,
      revPrev: function () { goPage(page - 1); }, revNext: function () { goPage(page + 1); },
      revPause: function () { c.setState({ revPaused: true }); }, revResume: function () { c.setState({ revPaused: false }); },
      revItems: REVIEWS.map(function (r, i) {
        return { name: r.name, text: r.text, initial: r.initial, label: (i + 1) + ' / ' + REVIEWS.length + ': ' + r.name,
          hidden: Math.floor(i / pv) === page ? 'false' : 'true' };
      }),
      revDots: dots
    };
  }

  window.HY = {
    reviewState: reviewState, mountReviews: mountReviews, unmountReviews: unmountReviews, reviews: reviews,
    ACCOUNT: ACCOUNT, USER: USER, account: account,
    lessons: lessons, lessonHref: lessonHref, load: load, save: save,
    cartGet: cartGet, cartSet: cartSet, cartAdd: cartAdd, money: money,
    steps: steps,
    SITE: SITE, COURSES: COURSES, REVIEWS: REVIEWS, ACCENTS: ACCENTS,
    stats: { courses: COURSES.length, lessons: Math.floor(totalLessons / 10) * 10 + '+' },
    course: function (slug) { return COURSES.filter(function (c) { return c.slug === slug; })[0]; },
    initState: initState, mount: mount, unmount: unmount, observeSections: observeSections,
    chrome: chrome, newsletter: newsletter, validate: validate
  };
})();
