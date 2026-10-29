(function () {
  "use strict";

  var theme = window.hyTheme;
  var root = document.querySelector("[data-theme-root]");
  var panel = document.getElementById("tema-paneli");
  var toggle = document.querySelector("[data-theme-toggle]");
  var icon = document.querySelector("[data-theme-icon]");
  var accentLabel = document.querySelector("[data-accent-label]");
  var menu = document.getElementById("mobil-menu");
  var menuBtn = document.querySelector("[data-menu-toggle]");
  var menuIcon = document.querySelector("[data-menu-icon]");
  function syncTheme() {
    if (!theme) return;
    var prefs = theme.get();
    if (icon) icon.className = "bi " + (prefs.theme === "dark" ? "bi-moon-stars" : "bi-sun");
    document.querySelectorAll("[data-theme-choice]").forEach(function (btn) {
      var on = btn.getAttribute("data-theme-choice") === prefs.theme;
      btn.classList.toggle("active", on);
      btn.classList.toggle("text-body-secondary", !on);
      btn.setAttribute("aria-checked", on ? "true" : "false");
    });
    document.querySelectorAll("[data-accent-choice]").forEach(function (btn) {
      var on = btn.getAttribute("data-accent-choice") === prefs.accent;
      btn.setAttribute("aria-checked", on ? "true" : "false");
      var mark = btn.querySelector("i");
      if (mark) mark.style.visibility = on ? "visible" : "hidden";
      btn.style.boxShadow = on
        ? "0 0 0 2px var(--bs-body-bg), 0 0 0 4px " + btn.getAttribute("data-hex")
        : "none";
      if (on && accentLabel) accentLabel.textContent = btn.getAttribute("data-label");
    });
  }

  function setPanel(open) {
    if (!panel || !toggle) return;
    panel.classList.toggle("show", open);
    toggle.setAttribute("aria-expanded", open ? "true" : "false");
  }

  // Hesap menüsü gibi basit açılır menüler: data-dropdown > data-dropdown-toggle + data-dropdown-menu
  var dropdowns = Array.prototype.map.call(document.querySelectorAll("[data-dropdown]"), function (dropdownRoot) {
    var button = dropdownRoot.querySelector("[data-dropdown-toggle]");
    var list = dropdownRoot.querySelector("[data-dropdown-menu]");
    function set(open) {
      list.classList.toggle("show", open);
      button.setAttribute("aria-expanded", open ? "true" : "false");
    }
    button.addEventListener("click", function () {
      set(!list.classList.contains("show"));
    });
    document.addEventListener("mousedown", function (event) {
      if (!dropdownRoot.contains(event.target)) set(false);
    });
    return { set: set };
  });

  function setMenu(open) {
    if (!menu || !menuBtn) return;
    menu.classList.toggle("show", open);
    menuBtn.setAttribute("aria-expanded", open ? "true" : "false");
    menuBtn.setAttribute("aria-label", open ? "Menüyü kapat" : "Menüyü aç");
    if (menuIcon) menuIcon.className = "bi " + (open ? "bi-x-lg" : "bi-list");
  }

  if (toggle) {
    toggle.addEventListener("click", function () {
      setPanel(!panel.classList.contains("show"));
    });
  }

  document.querySelectorAll("[data-theme-choice]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      theme.apply(btn.getAttribute("data-theme-choice"), theme.get().accent, true);
      syncTheme();
    });
  });

  document.querySelectorAll("[data-accent-choice]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      theme.apply(theme.get().theme, btn.getAttribute("data-accent-choice"), true);
      syncTheme();
    });
  });

  document.addEventListener("mousedown", function (event) {
    if (root && panel && panel.classList.contains("show") && !root.contains(event.target)) setPanel(false);
  });

  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape") {
      setPanel(false);
      setMenu(false);
      dropdowns.forEach(function (dropdown) { dropdown.set(false); });
    }
  });

  if (menuBtn) {
    menuBtn.addEventListener("click", function () {
      setMenu(!menu.classList.contains("show"));
    });
  }

  document.querySelectorAll("[data-nav]").forEach(function (link) {
    link.addEventListener("click", function () {
      setMenu(false);
    });
  });

  window.addEventListener("resize", function () {
    if (window.innerWidth >= 992) setMenu(false);
  });

  if ("IntersectionObserver" in window) {
    var observer = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (!entry.isIntersecting) return;
        document.querySelectorAll("[data-nav]").forEach(function (link) {
          var on = link.getAttribute("data-nav") === entry.target.id;
          link.classList.toggle("active", on);
          if (on) link.setAttribute("aria-current", "page");
          else link.removeAttribute("aria-current");
          var chevron = link.querySelector("[data-nav-chevron]");
          if (chevron) {
            chevron.classList.toggle("text-primary-emphasis", on);
            chevron.classList.toggle("text-body-tertiary", !on);
          }
        });
      });
    }, { rootMargin: "-45% 0px -50% 0px" });
    document.querySelectorAll("main > section[id]").forEach(function (section) {
      observer.observe(section);
    });
  }

  // Kurs sayfası bölüm menüsü: ekranda okunan bölümün bağlantısını aktif yapar.
  // scrollIntoView kullanılmaz; sayfayı da kaydırıp kullanıcının kaydırmasıyla çakışıyor.
  var sectionNav = document.querySelector("[data-section-nav]");
  var sectionLinks = Array.prototype.slice.call(document.querySelectorAll("[data-section-nav] a[href^='#']"));
  var currentSection = "";
  function setSection(id) {
    if (id === currentSection) return;
    currentSection = id;
    sectionLinks.forEach(function (link) {
      var on = link.hash === "#" + id;
      link.classList.toggle("active", on);
      if (on) link.setAttribute("aria-current", "true");
      else link.removeAttribute("aria-current");
      // Menü dar ekranda taşıyorsa yalnız menünün kendisi yatay kayar.
      if (on && sectionNav.scrollWidth > sectionNav.clientWidth) {
        sectionNav.scrollTo({ left: link.parentElement.offsetLeft - (sectionNav.clientWidth - link.offsetWidth) / 2 });
      }
    });
  }
  if (sectionLinks.length && "IntersectionObserver" in window) {
    var sectionObserver = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) setSection(entry.target.id);
      });
    }, { rootMargin: "-35% 0px -60% 0px" });
    sectionLinks.forEach(function (link) {
      var target = document.getElementById(link.hash.slice(1));
      if (target) sectionObserver.observe(target);
    });
  }

  // Bölüm menüsü taşıyorsa (mobil) kenarlarda solma ve ok gösterilir; ok menüyü kaydırır.
  var sectionBar = document.querySelector("[data-section-bar]");
  if (sectionBar && sectionNav) {
    function syncSectionMore() {
      var max = sectionNav.scrollWidth - sectionNav.clientWidth;
      sectionBar.classList.toggle("has-more-start", sectionNav.scrollLeft > 2);
      sectionBar.classList.toggle("has-more-end", sectionNav.scrollLeft < max - 2);
    }
    sectionBar.querySelectorAll("[data-section-scroll]").forEach(function (button) {
      button.addEventListener("click", function () {
        var step = Number(button.getAttribute("data-section-scroll")) * sectionNav.clientWidth * 0.6;
        sectionNav.scrollBy({ left: step, behavior: "smooth" });
      });
    });
    sectionNav.addEventListener("scroll", syncSectionMore, { passive: true });
    window.addEventListener("resize", syncSectionMore);
    syncSectionMore();
  }

  // Müfredat: bölümler açık başlar; tek düğmeyle hepsi kapanır ya da açılır.
  var foldToggle = document.querySelector("[data-fold-all]");
  if (foldToggle) {
    var folds = Array.prototype.slice.call(document.querySelectorAll(foldToggle.getAttribute("data-fold-all")));
    function syncFoldToggle() {
      var allOpen = folds.every(function (fold) { return fold.open; });
      foldToggle.textContent = allOpen ? "Tümünü kapat" : "Tümünü aç";
      foldToggle.setAttribute("aria-expanded", allOpen ? "true" : "false");
    }
    foldToggle.addEventListener("click", function () {
      var open = !folds.every(function (fold) { return fold.open; });
      folds.forEach(function (fold) { fold.open = open; });
      syncFoldToggle();
    });
    folds.forEach(function (fold) { fold.addEventListener("toggle", syncFoldToggle); });
    syncFoldToggle();
  }

  // Kurs sayfası (mobil): fiyat kartı ekranın üstünden çıkınca altta satın alma çubuğu görünür.
  var buyBar = document.querySelector("[data-buy-bar]");
  var buyCard = document.querySelector("[data-buy-card]");
  if (buyBar && buyCard && "IntersectionObserver" in window) {
    new IntersectionObserver(function (entries) {
      var passed = !entries[0].isIntersecting && entries[0].boundingClientRect.top < 0;
      buyBar.hidden = !passed;
      document.body.classList.toggle("has-buy-bar", passed);
    }).observe(buyCard);
  }

  // Önizleme şeridi: açılışta izlenen ders kartını şeridin ortasına getirir (ilk kart doğal olarak solda kalır).
  var previewStrip = document.querySelector("[data-preview-strip]");
  var previewCurrent = previewStrip && previewStrip.querySelector("[aria-current]");
  if (previewCurrent) {
    var stripBox = previewStrip.getBoundingClientRect();
    var cardBox = previewCurrent.getBoundingClientRect();
    previewStrip.scrollLeft += cardBox.left + cardBox.width / 2 - (stripBox.left + previewStrip.clientWidth / 2);
  }

  // Ders listesi: açılışta geçerli dersi listenin ortasına getirir (yalnız liste kayar, sayfa kaymaz).
  var sideScroll = document.querySelector("[data-side-scroll]");
  var sideCurrent = sideScroll && sideScroll.querySelector("details [aria-current]");
  if (sideCurrent && sideScroll.scrollHeight > sideScroll.clientHeight) {
    var sideBox = sideScroll.getBoundingClientRect();
    var itemBox = sideCurrent.getBoundingClientRect();
    sideScroll.scrollTop += itemBox.top - sideBox.top - (sideScroll.clientHeight - itemBox.height) / 2;
  }

  var carousel = document.querySelector("[data-hero]");
  if (carousel) {
    var track = carousel.querySelector("[data-hero-track]");
    var slides = carousel.querySelectorAll("[data-hero-slide]");
    var surface = carousel.querySelector("[data-hero-surface]");
    var index = 0;
    var startX = null;
    var startY = null;
    var swiped = 0;
    var elapsed = 0;
    var stamp = 0;
    var paused = false;
    var reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    var duration = 7000;

    function paint(amount) {
      var width = (Math.min(1, amount) * 100) + "%";
      var progress = carousel.querySelector("[data-hero-progress] > span");
      if (progress) progress.style.width = width;
      carousel.querySelectorAll("[data-hero-meter]").forEach(function (meter, meterIndex) {
        meter.firstElementChild.style.width = meterIndex === index ? width : "0%";
      });
    }

    function restart() {
      elapsed = 0;
      stamp = 0;
      paint(0);
    }

    function go(next) {
      var count = slides.length;
      index = ((next % count) + count) % count;
      track.style.transform = "translateX(" + (-index * 100) + "%)";
      slides.forEach(function (slide, slideIndex) {
        var current = slideIndex === index;
        slide.setAttribute("aria-hidden", current ? "false" : "true");
        slide.tabIndex = current ? 0 : -1;
      });
      var current = slides[index];
      var titleLink = carousel.querySelector("[data-hero-title-link]");
      titleLink.textContent = current.getAttribute("data-title");
      titleLink.href = current.getAttribute("href");
      carousel.querySelector("[data-hero-duration]").textContent = current.getAttribute("data-duration");
      carousel.querySelector("[data-hero-lessons]").textContent = current.getAttribute("data-lessons") + " ders";
      carousel.querySelector("[data-hero-price]").textContent = current.getAttribute("data-price");
      carousel.querySelector("[data-hero-inspect]").href = current.getAttribute("href");
      var cart = carousel.querySelector("[data-hero-cart]");
      cart.form.action = current.getAttribute("data-cart");
      cart.setAttribute("aria-label", current.getAttribute("data-cart-label"));
      var tags = carousel.querySelector("[data-hero-tags]");
      tags.replaceChildren();
      current.getAttribute("data-tags").split("|").forEach(function (tag) {
        var badge = document.createElement("span");
        badge.className = "badge rounded-1 border text-body-secondary fw-medium";
        badge.textContent = tag;
        tags.appendChild(badge);
      });
      carousel.querySelectorAll("[data-hero-thumb]").forEach(function (button, thumbIndex) {
        var on = thumbIndex === index;
        if (on) button.setAttribute("aria-current", "true");
        else button.removeAttribute("aria-current");
        button.classList.toggle("border-primary", on);
        button.classList.toggle("bg-primary-subtle", on);
        button.classList.toggle("text-body", on);
        button.classList.toggle("text-body-secondary", !on);
      });
      restart();
    }

    carousel.querySelector("[data-hero-prev]").addEventListener("click", function () { go(index - 1); });
    carousel.querySelector("[data-hero-next]").addEventListener("click", function () { go(index + 1); });
    carousel.querySelectorAll("[data-hero-thumb]").forEach(function (button) {
      button.addEventListener("click", function () {
        go(Number(button.getAttribute("data-hero-thumb")));
      });
    });
    carousel.addEventListener("keydown", function (event) {
      if (event.key === "ArrowRight") {
        event.preventDefault();
        go(index + 1);
      } else if (event.key === "ArrowLeft") {
        event.preventDefault();
        go(index - 1);
      }
    });
    surface.addEventListener("pointerdown", function (event) {
      startX = event.clientX;
      startY = event.clientY;
    });
    surface.addEventListener("pointerup", function (event) {
      if (startX == null) return;
      var dx = event.clientX - startX;
      var dy = event.clientY - startY;
      startX = null;
      if (Math.abs(dx) > 40 && Math.abs(dx) > Math.abs(dy)) {
        event.preventDefault();
        swiped = Date.now();
        go(index + (dx < 0 ? 1 : -1));
      }
    });
    surface.addEventListener("click", function (event) {
      if (swiped && Date.now() - swiped < 400) {
        event.preventDefault();
        event.stopPropagation();
      }
    }, true);

    carousel.addEventListener("mouseenter", function () { paused = true; });
    carousel.addEventListener("mouseleave", function () { paused = false; });
    carousel.addEventListener("focusin", function (event) {
      if (event.target.matches(":focus-visible")) paused = true;
    });
    carousel.addEventListener("focusout", function (event) {
      if (!carousel.contains(event.relatedTarget)) paused = false;
    });

    if (!reduced) {
      window.requestAnimationFrame(function loop(now) {
        var running = !paused && !document.hidden;
        if (running) {
          if (!stamp) stamp = now;
          var amount = (elapsed + (now - stamp)) / duration;
          if (amount >= 1) go(index + 1);
          else paint(amount);
        } else if (stamp) {
          elapsed += now - stamp;
          stamp = 0;
        }
        window.requestAnimationFrame(loop);
      });
    }
  }

  var reviews = document.querySelector("[data-reviews]");
  var reviewsStarted = false;

  function perView() {
    return window.matchMedia("(min-width: 768px)").matches ? 3 : 1;
  }

  function startReviews() {
    if (!reviews || reviewsStarted) return;
    reviewsStarted = true;
    var skeleton = reviews.querySelector("[data-review-skeleton]");
    var ready = reviews.querySelector("[data-review-ready]");
    var track = reviews.querySelector("[data-review-track]");
    var slides = reviews.querySelectorAll("[data-review-slide]");
    var dots = reviews.querySelector("[data-review-dots]");
    var pos = reviews.querySelector("[data-review-pos]");
    var prev = reviews.querySelector("[data-review-prev]");
    var next = reviews.querySelector("[data-review-next]");
    var page = 0;
    var paused = false;
    var timer = null;
    var reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    function pageCount() {
      return Math.max(1, Math.ceil(slides.length / perView()));
    }

    function renderDots() {
      var count = pageCount();
      dots.replaceChildren();
      for (var i = 0; i < count; i++) {
        var button = document.createElement("button");
        button.type = "button";
        button.className = "btn border-0 p-2";
        button.setAttribute("aria-label", (i + 1) + ". yorum sayfası");
        if (i === page) button.setAttribute("aria-current", "true");
        var mark = document.createElement("span");
        mark.className = "d-block rounded-1";
        mark.style.width = i === page ? "24px" : "8px";
        mark.style.height = "4px";
        mark.style.background = i === page ? "var(--bs-primary)" : "var(--bs-border-color)";
        mark.style.transition = "width .3s";
        button.appendChild(mark);
        button.addEventListener("click", (function (index) {
          return function () { go(index); };
        })(i));
        dots.appendChild(button);
      }
    }

    function go(nextPage) {
      var count = pageCount();
      page = ((nextPage % count) + count) % count;
      var view = perView();
      track.style.transform = "translateX(" + (-page * 100) + "%)";
      slides.forEach(function (slide, index) {
        var visible = Math.floor(index / view) === page;
        slide.setAttribute("aria-hidden", visible ? "false" : "true");
      });
      if (pos) pos.textContent = (page + 1) + " / " + count;
      renderDots();
    }

    function play() {
      if (timer || reduced) return;
      timer = window.setInterval(function () {
        if (paused || document.hidden) return;
        go(page + 1);
      }, 7000);
    }

    function reveal() {
      skeleton.classList.add("d-none");
      skeleton.setAttribute("aria-busy", "false");
      ready.classList.remove("d-none");
      dots.classList.remove("d-none");
      dots.classList.add("d-flex");
      prev.disabled = false;
      next.disabled = false;
      go(0);
      play();
    }

    reviews.addEventListener("mouseenter", function () { paused = true; });
    reviews.addEventListener("mouseleave", function () { paused = false; });
    reviews.addEventListener("focusin", function () { paused = true; });
    reviews.addEventListener("focusout", function () { paused = false; });
    prev.addEventListener("click", function () { go(page - 1); });
    next.addEventListener("click", function () { go(page + 1); });
    window.matchMedia("(min-width: 768px)").addEventListener("change", function () {
      go(0);
    });

    reveal();
  }

  if ("IntersectionObserver" in window) {
    var revealObserver = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (!entry.isIntersecting) return;
        entry.target.classList.add("is-visible");
        revealObserver.unobserve(entry.target);
      });
    }, { threshold: 0, rootMargin: "0px 0px -35% 0px" });
    // Yorum listesi bölüm göründüğü anda başlar; sayfanın en altındaki bölüm ekranın üst kısmına hiç gelemeyebilir.
    var reviewsObserver = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (!entry.isIntersecting) return;
        entry.target.classList.add("is-visible");
        startReviews();
        reviewsObserver.unobserve(entry.target);
      });
    }, { threshold: 0.2 });
    window.requestAnimationFrame(function () {
      document.querySelectorAll("main > section").forEach(function (section) {
        revealObserver.observe(section);
      });
      document.querySelectorAll("[data-reviews]").forEach(function (section) {
        reviewsObserver.observe(section);
      });
    });
  } else {
    document.querySelectorAll("main > section").forEach(function (section) {
      section.classList.add("is-visible");
    });
    startReviews();
  }

  // Video.js oynatıcısı. Video, yüklendiği platformdan oynar: Bunny Stream'de HLS (<hlsjs-video>), Vimeo'da Vimeo'nun
  // kendi oynatıcısı (<vimeo-video>). Paket büyük olduğu için yalnız gerektiğinde yüklenir
  // (frontend/ → static_files/js/videojs/player.js). Dersler 720p, tanıtım videosu en yüksek kalitede açılır;
  // kalite menüsünden değiştirilebilir.
  var DEFAULT_QUALITY_HEIGHT = 720;
  // Django tüm sayfalarda "Referrer-Policy: same-origin" gönderir; alan adı kısıtlı Vimeo videoları referrer olmadan
  // oynamaz. Yalnız Vimeo bağlantısı için Vimeo'nun kendi gömme kodundaki politika kullanılır.
  var VIMEO_REFERRER_POLICY = "strict-origin-when-cross-origin";

  function mountPlayer(target, options) {
    if (options.platform === "vimeo") return createPlayer(target, options);
    // HLS motoru CDN reddettiğinde (ör. 403) hata vermeden boş kalıyor; liste önce yoklanır, alınamazsa açıklama gösterilir.
    return fetch(options.src, { credentials: "omit" }).then(function (response) {
      if (response.ok) return createPlayer(target, options);
      console.warn("Video alınamadı (" + response.status + "): Bunny CDN bu sayfanın adresine izin vermiyor olabilir. Port içeren adresler (ör. :8001) reddedilir.");
      showPlayerError(target);
      return null;
    });
  }

  function createPlayer(target, options) {
    return import(options.playerSrc).then(function (videojs) {
      // Oynatıcı metinleri <media-i18n> sağlayıcısından çevrilir; dil sayfanın dilinden gelir.
      var i18n = document.createElement("media-i18n");
      var player = document.createElement("video-player");
      var skin = document.createElement("video-skin");
      var vimeo = options.platform === "vimeo";
      var media = document.createElement(vimeo ? "vimeo-video" : "hlsjs-video");
      i18n.className = "d-block";
      i18n.setAttribute("lang", document.documentElement.lang || "tr");
      player.className = "d-block hy-video";
      skin.className = "hy-video-skin";
      media.setAttribute("src", options.src);
      media.setAttribute("playsinline", "");
      media.setAttribute("crossorigin", "");
      if (options.poster) media.setAttribute("poster", options.poster);
      if (options.autoplay) {
        // Tıklamayla açıldığı için sesli başlar; tarayıcı sesli otomatik oynatmayı reddederse sessiz başlatılır.
        media.addEventListener("loadedmetadata", function () {
          var started = media.play();
          if (started && started.catch) {
            started.catch(function () {
              media.muted = true;
              media.play();
            });
          }
        }, { once: true });
      }
      (options.tracks || []).forEach(function (item) {
        var track = document.createElement("track");
        track.kind = "subtitles";
        track.src = item.src;
        track.srclang = item.lang;
        track.label = item.label;
        media.appendChild(track);
      });
      // "auto": kaliteyi oynatıcı bağlantıya göre seçer; diğerleri (720, "highest") ilk yüklemede seçilir.
      var quality = options.quality || DEFAULT_QUALITY_HEIGHT;
      if (vimeo) {
        videojs.enableVimeoQuality(media, quality === "auto" ? null : quality);
      } else if (quality !== "auto") {
        videojs.preferQuality(media, quality);
      }
      // Video alınamazsa (ör. CDN izin vermedi) oynatıcı yerine açıklama gösterilir.
      media.addEventListener("error", function () { showPlayerError(i18n); }, { once: true });
      skin.appendChild(media);
      player.appendChild(skin);
      i18n.appendChild(player);
      target.replaceWith(i18n);
      // Vimeo iframe'i öğe sayfaya eklenince kurulur; referrer politikası iframe yüklenmeden önce verilir.
      var frame = vimeo && media.shadowRoot && media.shadowRoot.querySelector("iframe");
      if (frame) frame.referrerPolicy = VIMEO_REFERRER_POLICY;
      return media;
    });
  }

  function showPlayerError(element) {
    var box = document.createElement("div");
    box.className = "d-flex flex-column align-items-center justify-content-center text-center text-white bg-black p-4";
    box.setAttribute("role", "alert");
    box.innerHTML = '<i class="bi bi-exclamation-octagon fs-1" aria-hidden="true"></i><p class="mt-2 mb-0">Video oynatılamadı. Sayfayı yenileyip tekrar dene; sorun sürerse bize yaz.</p>';
    // Ders sayfasında yer tutucu zaten 16:9 kutunun içinde; tanıtım düğmesinin yerine 16:9 kutu kurulur.
    var holder = box;
    if (!element.parentElement.classList.contains("ratio")) {
      holder = document.createElement("div");
      holder.className = "ratio ratio-16x9 bg-black";
      holder.appendChild(box);
    }
    element.replaceWith(holder);
  }

  function playerFailed() {
    if (window.hyToast) window.hyToast("error", "Video yüklenemedi. Sayfayı yenileyip tekrar dene.");
  }

  // Tanıtım videosu: görsele tıklanınca ekranın %95'ini kaplayan pencerede açılır ve kendiliğinden başlar.
  // Videonun altında kurs sayfasına ve önizleme derslerine bağlantı vardır.
  // Esc, ✕ ya da pencere dışına tıklama kapatır; kapanınca oynatıcı kaldırılır (ses kesilir) ve odak görsele döner.
  var previewDialog = null;
  var previewTrigger = null;

  function closePreview() {
    // Kaydırma kilidi hemen kalkar; "close" olayı sonra gelir ve bağlantının bölüme kaydırmasını engellememeli.
    document.documentElement.classList.remove("hy-dialog-open");
    if (previewDialog && previewDialog.open) previewDialog.close();
  }

  function previewDialogElement() {
    if (previewDialog) return previewDialog;
    previewDialog = document.createElement("dialog");
    previewDialog.className = "hy-video-dialog";
    previewDialog.setAttribute("aria-label", "Tanıtım videosu");
    previewDialog.addEventListener("click", function (event) {
      var link = event.target.closest("[data-dialog-link]");
      if (link) {
        // Önce pencere kapanır, sonra bağlantıya gidilir; aynı sayfadaki bölümse sayfa oraya kayar.
        event.preventDefault();
        previewTrigger = null;
        closePreview();
        var target = new URL(link.href, window.location.href);
        if (target.pathname !== window.location.pathname || !target.hash) {
          window.location.href = target.href;
          return;
        }
        // Pencere kapanınca tarayıcı odağı görsele geri verip sayfayı oraya kaydırır; bölüme ondan sonra gidilir.
        history.pushState(null, "", target.hash);
        setTimeout(function () {
          var section = document.getElementById(target.hash.slice(1));
          if (section) section.scrollIntoView({ behavior: "smooth", block: "start" });
        }, 0);
        return;
      }
      if (event.target === previewDialog || event.target.closest("[data-dialog-close]")) closePreview();
    });
    previewDialog.addEventListener("close", function () {
      previewDialog.innerHTML = "";
      document.documentElement.classList.remove("hy-dialog-open");
      if (previewTrigger) previewTrigger.focus();
    });
    document.body.appendChild(previewDialog);
    return previewDialog;
  }

  function previewLinks(trigger) {
    var links = [];
    var courseUrl = trigger.getAttribute("data-course-url");
    var previewsUrl = trigger.getAttribute("data-previews-url");
    if (courseUrl) {
      links.push('<a class="btn btn-light" data-dialog-link href="' + courseUrl + '">Eğitim detay sayfasını incele <i class="bi bi-arrow-right ms-1" aria-hidden="true"></i></a>');
    }
    if (previewsUrl) {
      links.push('<a class="btn btn-outline-light" data-dialog-link href="' + previewsUrl + '"><i class="bi bi-play-circle me-1" aria-hidden="true"></i>Önizleme videolarını incele</a>');
    }
    return links.length ? '<div class="hy-video-dialog-actions d-flex flex-wrap justify-content-center gap-2">' + links.join("") + "</div>" : "";
  }

  document.querySelectorAll("[data-preview-video]").forEach(function (trigger) {
    trigger.setAttribute("aria-haspopup", "dialog");
    trigger.addEventListener("click", function () {
      var dialog = previewDialogElement();
      previewTrigger = trigger;
      dialog.innerHTML =
        '<button type="button" class="btn btn-dark btn-sm rounded-circle hy-video-dialog-close" data-dialog-close aria-label="Kapat"><i class="bi bi-x-lg" aria-hidden="true"></i></button>' +
        '<div class="hy-video-dialog-body"><div class="ratio ratio-16x9"><div class="d-flex align-items-center justify-content-center text-white-50" data-dialog-player>' +
        '<span class="spinner-border" aria-hidden="true"></span><span class="visually-hidden">Video yükleniyor</span></div></div>' +
        previewLinks(trigger) + "</div>";
      document.documentElement.classList.add("hy-dialog-open");
      dialog.showModal();
      mountPlayer(dialog.querySelector("[data-dialog-player]"), {
        playerSrc: trigger.getAttribute("data-player-src"),
        platform: trigger.getAttribute("data-video-platform"),
        src: trigger.getAttribute("data-preview-video"),
        poster: trigger.getAttribute("data-poster"),
        autoplay: true,
        // Tanıtım videosu en yüksek kalitede açılır (dersler 720p).
        quality: "highest",
      }).catch(function () {
        closePreview();
        playerFailed();
      });
    });
  });

  // Ders videosu: sayfa açılınca yer tutucunun yerine oynatıcı kurulur; altyazılar JSON olarak gelir.
  document.querySelectorAll("[data-lesson-video]").forEach(function (holder) {
    var tracks = [];
    var preferences = {};
    try {
      tracks = JSON.parse(holder.getAttribute("data-tracks") || "[]");
      preferences = JSON.parse(holder.getAttribute("data-preferences") || "{}");
    } catch (error) {
      tracks = [];
    }
    var preferencesUrl = holder.getAttribute("data-preferences-url");
    mountPlayer(holder, {
      playerSrc: holder.getAttribute("data-player-src"),
      platform: holder.getAttribute("data-video-platform"),
      src: holder.getAttribute("data-lesson-video"),
      poster: holder.getAttribute("data-poster"),
      tracks: tracks,
      quality: preferences.quality,
    }).then(function (media) {
      if (!media) return;
      watchCompletion(media);
      applyPreferences(media, preferences);
      if (preferencesUrl) watchPreferences(media, preferences, preferencesUrl);
    }).catch(playerFailed);
  });

  // Oynatıcı tercihleri (hesap ayarları → Video oynatma): hız, altyazı ve oynatınca tam ekran. Kalite createPlayer'da.
  function captionTracks(media) {
    return media.textTracks
      ? Array.from(media.textTracks).filter(function (track) {
          return track.kind === "subtitles" || track.kind === "captions";
        })
      : [];
  }

  function applyPreferences(media, preferences) {
    var subtitlesApplied = false;
    function applySubtitles() {
      if (subtitlesApplied || !preferences.subtitles) return;
      var tracks = captionTracks(media);
      if (!tracks.length) return;
      subtitlesApplied = true;
      var track = tracks.filter(function (item) { return item.language === preferences.subtitleLanguage; })[0] || tracks[0];
      tracks.forEach(function (item) { item.mode = item === track ? "showing" : "disabled"; });
    }
    media.addEventListener("loadedmetadata", function () {
      if (preferences.rate && media.playbackRate !== preferences.rate) media.playbackRate = preferences.rate;
      applySubtitles();
    });
    var trackLists = [];
    function bindTrackList() {
      var tracks = media.textTracks;
      if (!tracks || !tracks.addEventListener || trackLists.indexOf(tracks) !== -1) return;
      trackLists.push(tracks);
      tracks.addEventListener("addtrack", applySubtitles);
    }
    bindTrackList();
    media.addEventListener("loadedmetadata", bindTrackList);
    // Tam ekran oynat'a basılınca (kullanıcı hareketiyle) bir kez açılır; tarayıcı reddederse sessizce geçilir.
    var fullscreenTried = false;
    media.addEventListener("play", function () {
      if (!preferences.fullscreen || fullscreenTried || document.fullscreenElement) return;
      fullscreenTried = true;
      var player = media.closest("video-player");
      if (player && player.requestFullscreen) player.requestFullscreen().catch(function () {});
    });
  }

  // CSRF anahtarı base şablondaki hx-headers'tan okunur (HTMX dışı fetch istekleri için).
  function csrfToken() {
    try {
      return JSON.parse(document.body.getAttribute("hx-headers") || "{}")["x-csrftoken"] || "";
    } catch (error) {
      return "";
    }
  }

  // Kullanıcı oynatıcıda hızı, kaliteyi ya da altyazıyı değiştirince tercih arka planda kaydedilir. Tercihi uygularken
  // oluşan değişiklikler kayıtlı değere eşit olduğu için yeniden gönderilmez.
  function watchPreferences(media, preferences, url) {
    var pending = {};
    var timer = null;
    function save(changes) {
      Object.keys(changes).forEach(function (key) { pending[key] = changes[key]; });
      clearTimeout(timer);
      timer = setTimeout(function () {
        var data = new FormData();
        Object.keys(pending).forEach(function (key) { data.append(key, pending[key]); });
        pending = {};
        fetch(url, { method: "POST", body: data, headers: { "X-CSRFToken": csrfToken() }, credentials: "same-origin" }).catch(function () {});
      }, 700);
    }

    media.addEventListener("ratechange", function () {
      var rate = Math.round(media.playbackRate * 100) / 100;
      if (rate === preferences.rate) return;
      preferences.rate = rate;
      save({ playback_rate: String(rate) });
    });

    // Kaynak yeniden yüklenirse oynatıcı yeni bir kalite listesi açabilir; her seferinde güncel listeye bağlanılır.
    var watchedList = null;
    media.addEventListener("loadedmetadata", function () {
      var list = media.videoRenditions;
      if (list === watchedList || !list || !list.addEventListener) return;
      watchedList = list;
      list.addEventListener("change", function () {
        if (list !== watchedList) return;
        // Liste yalnız döngüyle okunabilir (Vimeo kalite listesinde dizin yok).
        var renditions = Array.from(list);
        var selected = renditions[list.selectedIndex];
        var value = selected ? String(selected.height) : "auto";
        if (preferences.quality === "highest" && selected) {
          var highest = Math.max.apply(null, renditions.map(function (item) { return item.height || 0; }));
          if (selected.height === highest) return;
        }
        if (String(preferences.quality) === value) return;
        preferences.quality = value === "auto" ? "auto" : Number(value);
        save({ quality: value });
      });
    });

    // Altyazı listesi de oynatıcı kurulurken değişebilir; meta veri gelince güncel listeye bağlanılır.
    var watchedTracks = null;
    function onTracksChange(event) {
      if (event.currentTarget !== watchedTracks) return;
      var showing = captionTracks(media).filter(function (track) { return track.mode === "showing"; })[0];
      var enabled = Boolean(showing);
      var language = showing ? showing.language : preferences.subtitleLanguage;
      if (enabled === Boolean(preferences.subtitles) && (!enabled || language === preferences.subtitleLanguage)) return;
      preferences.subtitles = enabled;
      preferences.subtitleLanguage = language;
      save({ subtitles_enabled: enabled ? "true" : "false", subtitle_language: language });
    }
    function bindTracks() {
      var tracks = media.textTracks;
      if (tracks === watchedTracks || !tracks || !tracks.addEventListener) return;
      watchedTracks = tracks;
      tracks.addEventListener("change", onTracksChange);
    }
    bindTracks();
    media.addEventListener("loadedmetadata", bindTracks);
  }

  // Ortak pencere (ör. "Tüm yorumlar"): içerik yüklenince açılır; ✕, Esc ya da dışarı tıklama kapatır.
  var siteDialog = document.getElementById("site-dialog");
  if (siteDialog) {
    document.body.addEventListener("htmx:afterSwap", function (event) {
      if (event.detail.target.id !== "site-dialog-body" || siteDialog.open) return;
      document.documentElement.classList.add("hy-dialog-open");
      siteDialog.showModal();
    });
    siteDialog.addEventListener("click", function (event) {
      if (event.target === siteDialog || event.target.closest("[data-dialog-close]")) siteDialog.close();
    });
    siteDialog.addEventListener("close", function () {
      document.documentElement.classList.remove("hy-dialog-open");
      document.getElementById("site-dialog-body").innerHTML = "";
    });
  }

  // Ders tamamlama: video durdurulmadan 5 sn oynayınca ders "tamamlandı" olarak işaretlenir. Durdurulursa sayaç
  // baştan başlar. Ders zaten tamamlandıysa ya da kullanıcı bu sayfada düğmeyle elle seçim yaptıysa denenmez.
  var AUTO_COMPLETE_MS = 5000;
  function watchCompletion(media) {
    var timer = null;
    function button() {
      return document.getElementById("lesson-complete");
    }
    function stop() {
      clearTimeout(timer);
      timer = null;
    }
    media.addEventListener("playing", function () {
      var target = button();
      if (timer || !target || target.getAttribute("data-completed") === "true" || target.hasAttribute("data-manual")) return;
      timer = setTimeout(function () {
        timer = null;
        var current = button();
        if (media.paused || !current || current.getAttribute("data-completed") === "true" || current.hasAttribute("data-manual")) return;
        // Kaynak düğme: CSRF başlığı (body hx-headers) ondan devralınır.
        window.htmx.ajax("POST", current.getAttribute("hx-post"), {
          source: current,
          target: current,
          swap: "outerHTML",
          values: { done: "1", auto: "1" },
        });
      }, AUTO_COMPLETE_MS);
    });
    ["pause", "ended", "emptied"].forEach(function (name) { media.addEventListener(name, stop); });
  }

  // Bildirimler: Django mesajları sağ üstte kendiliğinden kapanan toast olarak gösterilir (SweetAlert2).
  var toastIcons = { success: "success", info: "info", warning: "warning", error: "error", debug: "info" };
  var toast = window.Swal && window.Swal.mixin({
    toast: true,
    position: "top-end",
    showConfirmButton: false,
    showCloseButton: true,
    timer: 3500,
    timerProgressBar: true,
    customClass: { container: "hy-toast-container", popup: "hy-toast" },
    didOpen: function (popup) {
      popup.addEventListener("mouseenter", window.Swal.stopTimer);
      popup.addEventListener("mouseleave", window.Swal.resumeTimer);
    }
  });

  window.hyToast = function (level, text) {
    if (!toast) return Promise.resolve();
    // Üst çubuğun yüksekliği sayfaya ve ekran genişliğine göre değişir; bildirim hep altında açılır.
    var bar = document.querySelector("nav.navbar");
    var top = bar ? Math.max(bar.getBoundingClientRect().bottom, 0) : 0;
    document.documentElement.style.setProperty("--hy-toast-top", top + 8 + "px");
    return toast.fire({ icon: toastIcons[level] || "info", title: text });
  };

  var toastData = document.querySelector("template[data-toasts]");
  if (toastData) {
    Array.prototype.reduce.call(toastData.content.querySelectorAll("[data-toast-level]"), function (queue, item) {
      return queue.then(function () {
        return window.hyToast(item.getAttribute("data-toast-level"), item.textContent);
      });
    }, Promise.resolve());
  }

  syncTheme();
})();
