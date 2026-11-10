/* Stüdyo izometrik pano: sahneler ekrana girene kadar bekletilir (.is-waiting), girince kuleler büyür; [data-count]
   sayıları sıfırdan sayılır. JS yoksa kuleler hemen büyür, sayılar son haliyle görünür. */
(function () {
  "use strict";

  var reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var format = new Intl.NumberFormat("tr-TR");

  function count(el) {
    var target = parseInt(el.getAttribute("data-count"), 10);
    if (!target || reduced) return;
    var start = null;
    function step(now) {
      if (start === null) start = now;
      var p = Math.min((now - start) / 1100, 1);
      el.textContent = format.format(Math.round(target * (1 - Math.pow(1 - p, 3))));
      if (p < 1) window.requestAnimationFrame(step);
    }
    el.textContent = "0";
    window.requestAnimationFrame(step);
  }

  function live(el) {
    if (el.hasAttribute("data-iso-scene")) el.classList.remove("is-waiting");
    if (el.hasAttribute("data-count")) count(el);
  }

  var pending = Array.prototype.slice.call(document.querySelectorAll("[data-iso-scene], [data-count]"));
  pending.forEach(function (el) {
    if (el.hasAttribute("data-iso-scene")) el.classList.add("is-waiting");
  });

  var queued = false;
  function check() {
    queued = false;
    var edge = window.innerHeight * 0.9;
    pending = pending.filter(function (el) {
      var box = el.getBoundingClientRect();
      if (box.top < edge && box.bottom > 0) {
        live(el);
        return false;
      }
      return true;
    });
    if (!pending.length) {
      window.removeEventListener("scroll", queue);
      window.removeEventListener("resize", queue);
    }
  }
  function queue() {
    if (queued) return;
    queued = true;
    window.requestAnimationFrame(check);
  }

  window.addEventListener("scroll", queue, { passive: true });
  window.addEventListener("resize", queue);
  queue();
})();
