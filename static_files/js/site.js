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
      cart.href = current.getAttribute("data-cart");
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

    if (reduced) reveal();
    else window.setTimeout(reveal, 900);
  }

  if ("IntersectionObserver" in window) {
    var revealObserver = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (!entry.isIntersecting) return;
        entry.target.classList.add("is-visible");
        if (entry.target.hasAttribute("data-reviews")) startReviews();
        revealObserver.unobserve(entry.target);
      });
    }, { threshold: 0, rootMargin: "0px 0px -35% 0px" });
    window.requestAnimationFrame(function () {
      document.querySelectorAll("main > section").forEach(function (section) {
        revealObserver.observe(section);
      });
    });
  } else {
    document.querySelectorAll("main > section").forEach(function (section) {
      section.classList.add("is-visible");
    });
    startReviews();
  }

  syncTheme();
})();
