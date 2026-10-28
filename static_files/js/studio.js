// Stüdyo paneli: dosya gönderim ilerlemesi, form kapatma, sunucudan gelen bildirimler,
// içerik düzenleyicide sürükle-bırak (video yükleme, sıralama, kategoriler arası taşıma, satıra SRT bırakma).
(function () {
  "use strict";

  function toast(level, text) {
    if (window.hyToast) window.hyToast(level, text);
  }

  // Sunucu HX-Trigger ile { level, text } gönderir; bildirim site.js'teki toast ile gösterilir.
  document.body.addEventListener("hy:toast", function (event) {
    toast(event.detail.level, event.detail.text);
  });

  // Tarayıcıdan sunucuya gönderim ilerlemesi; Vimeo'ya gönderim ilerlemesini ders satırı kendisi yeniler.
  document.body.addEventListener("htmx:xhr:progress", function (event) {
    var form = event.target.closest && event.target.closest("[data-upload-form]");
    if (!form || !event.detail.lengthComputable) return;
    var bar = form.querySelector("[data-upload-progress]");
    var percent = Math.round((event.detail.loaded / event.detail.total) * 100);
    bar.classList.remove("d-none");
    bar.setAttribute("aria-valuenow", percent);
    bar.firstElementChild.style.width = percent + "%";
    bar.firstElementChild.textContent = "%" + percent;
  });

  // Gönderim sürerken düğmeler kilitlenir ve sayfadan çıkmadan önce uyarılır.
  var pending = 0;
  var uploadQueue = [];
  function uploadForm(event) {
    return event.detail.elt && event.detail.elt.matches && event.detail.elt.matches("[data-upload-form]") ? event.detail.elt : null;
  }
  document.body.addEventListener("htmx:beforeRequest", function (event) {
    var form = uploadForm(event);
    if (!form) return;
    pending += 1;
    form.querySelectorAll("button").forEach(function (button) { button.disabled = true; });
  });
  document.body.addEventListener("htmx:afterRequest", function (event) {
    var form = uploadForm(event);
    if (!form) return;
    pending = Math.max(0, pending - 1);
    form.querySelectorAll("button").forEach(function (button) { button.disabled = false; });
  });
  window.addEventListener("beforeunload", function (event) {
    if (!pending && !uploadQueue.length) return;
    event.preventDefault();
    event.returnValue = "";
  });

  document.addEventListener("click", function (event) {
    var close = event.target.closest("[data-form-close]");
    if (close) close.closest('[id$="-form"]').innerHTML = "";
  });

  // ---- İçerik düzenleyici ----

  var VIDEO_FILE = /\.(mp4|mov|m4v|mkv|webm|avi)$/i;
  var SUBTITLE_FILE = /\.(srt|vtt)$/i;

  function csrfToken() {
    try {
      return JSON.parse(document.body.getAttribute("hx-headers") || "{}")["x-csrftoken"] || "";
    } catch (error) {
      return "";
    }
  }

  function within(scope, selector) {
    var found = Array.prototype.slice.call(scope.querySelectorAll(selector));
    if (scope.matches && scope.matches(selector)) found.unshift(scope);
    return found;
  }

  // Sıra numaraları (1.1, 1.2 ...) ve kategori video sayıları sayfadaki düzene göre yeniden yazılır.
  function renumber(root) {
    var offset = parseInt(root.getAttribute("data-section-offset") || "1", 10);
    root.querySelectorAll("[data-section-id]").forEach(function (section, index) {
      var number = offset + index;
      var lessons = section.querySelectorAll("[data-lesson-id]");
      var sectionNo = section.querySelector("[data-section-no]");
      var count = section.querySelector("[data-section-count]");
      if (sectionNo) sectionNo.textContent = number + ".";
      if (count) count.textContent = lessons.length + " video";
      lessons.forEach(function (lesson, lessonIndex) {
        var lessonNo = lesson.querySelector("[data-lesson-no]");
        if (lessonNo) lessonNo.textContent = number + "." + (lessonIndex + 1);
      });
    });
  }

  function renumberAll() {
    document.querySelectorAll("[data-structure]").forEach(renumber);
  }

  // Düzen her sürüklemeden sonra tümüyle gönderilir; sunucu bölüm ve ders sıralarını buna göre yazar.
  function saveStructure(root) {
    var sections = Array.prototype.map.call(root.querySelectorAll("[data-section-id]"), function (section) {
      return {
        id: section.getAttribute("data-section-id"),
        lessons: Array.prototype.map.call(section.querySelectorAll("[data-lesson-id]"), function (lesson) {
          return lesson.getAttribute("data-lesson-id");
        }),
      };
    });
    renumber(root);
    fetch(root.getAttribute("data-structure-url"), {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRFToken": csrfToken() },
      body: JSON.stringify({ sections: sections, reorder_sections: root.getAttribute("data-reorder-sections") !== "false" }),
    })
      .then(function (response) {
        if (!response.ok) throw new Error(response.status);
      })
      .catch(function () {
        toast("error", "Sıralama kaydedilemedi; sayfa yenileniyor.");
        setTimeout(function () { window.location.reload(); }, 1500);
      });
  }

  function moved(event) {
    return event.from !== event.to || event.oldIndex !== event.newIndex;
  }

  function initSortables(scope) {
    if (!window.Sortable) return;
    within(scope, "[data-sortable-sections]:not([data-sortable-ready])").forEach(function (list) {
      list.setAttribute("data-sortable-ready", "");
      window.Sortable.create(list, {
        handle: ".studio-section-handle",
        draggable: "[data-section-id]",
        animation: 150,
        onEnd: function (event) {
          if (moved(event)) saveStructure(list.closest("[data-structure]"));
        },
      });
    });
    within(scope, "[data-sortable-lessons]:not([data-sortable-ready])").forEach(function (list) {
      list.setAttribute("data-sortable-ready", "");
      window.Sortable.create(list, {
        group: "lessons",
        handle: ".studio-lesson-handle",
        draggable: "[data-lesson-id]",
        animation: 150,
        onEnd: function (event) {
          if (moved(event)) saveStructure(event.to.closest("[data-structure]"));
        },
      });
    });
  }

  function contentAdded(element) {
    initSortables(element);
    renumberAll();
  }

  if (window.htmx) window.htmx.onLoad(contentAdded);
  document.body.addEventListener("htmx:afterSettle", renumberAll);

  // Video yükleme: dosyalar adlarına göre sıralanır ve sırayla, tek tek gönderilir; her biri bir ders satırı olur.

  var uploading = false;

  function enqueue(zone, fileList) {
    var files = Array.prototype.filter.call(fileList, function (file) { return VIDEO_FILE.test(file.name); });
    var skipped = fileList.length - files.length;
    if (skipped) toast("warning", skipped + " dosya video olmadığı için atlandı.");
    files.sort(function (a, b) { return a.name.localeCompare(b.name, "tr", { numeric: true }); });
    var list = zone.querySelector("[data-upload-list]");
    files.forEach(function (file) {
      var item = document.createElement("li");
      item.innerHTML =
        '<div class="d-flex justify-content-between gap-2"><span class="text-truncate" data-upload-name></span>' +
        '<span class="text-body-secondary text-nowrap" data-upload-state>Bekliyor</span></div>' +
        '<div class="progress studio-progress mt-1" role="progressbar" aria-valuemin="0" aria-valuemax="100"><div class="progress-bar" style="width:0%"></div></div>';
      item.querySelector("[data-upload-name]").textContent = file.name;
      list.appendChild(item);
      uploadQueue.push({ zone: zone, file: file, item: item });
    });
    pump();
  }

  function pump() {
    if (uploading || !uploadQueue.length) return;
    uploading = true;
    send(uploadQueue.shift()).then(function () {
      uploading = false;
      pump();
    });
  }

  function send(job) {
    var state = job.item.querySelector("[data-upload-state]");
    var progress = job.item.querySelector("[role=progressbar]");
    var bar = progress.firstElementChild;
    var data = new FormData();
    data.append("file", job.file);
    return new Promise(function (resolve) {
      var xhr = new XMLHttpRequest();
      xhr.open("POST", job.zone.getAttribute("data-upload-url"));
      xhr.setRequestHeader("X-CSRFToken", csrfToken());
      xhr.upload.onprogress = function (event) {
        if (!event.lengthComputable) return;
        var percent = Math.round((event.loaded / event.total) * 100);
        bar.style.width = percent + "%";
        progress.setAttribute("aria-valuenow", percent);
        state.textContent = "%" + percent;
      };
      xhr.onload = function () {
        if (xhr.status !== 200) {
          fail(job.item, state, bar, xhr.responseText || "Sunucu hatası (" + xhr.status + ")");
          return resolve();
        }
        state.textContent = "Sunucuda";
        placeLesson(xhr).then(function () {
          job.item.remove();
          resolve();
        });
      };
      xhr.onerror = function () {
        fail(job.item, state, bar, "Bağlantı koptu");
        resolve();
      };
      xhr.send(data);
    });
  }

  function fail(item, state, bar, message) {
    item.classList.add("text-danger-emphasis");
    bar.classList.add("bg-danger");
    state.textContent = message;
  }

  // Yeni ders satırı kendi kategorisinin sonuna eklenir; kategori sayfada yoksa (ilk "Genel") bloğu istenir.
  function placeLesson(xhr) {
    var list = document.getElementById("section-" + xhr.getResponseHeader("X-Section-Id") + "-lessons");
    if (list) {
      list.insertAdjacentHTML("beforeend", xhr.responseText);
      window.htmx.process(list.lastElementChild);
      renumberAll();
      return Promise.resolve();
    }
    var sections = document.querySelector("[data-sortable-sections]");
    if (!sections) return Promise.resolve();
    return fetch(xhr.getResponseHeader("X-Section-Block-Url"), { headers: { "HX-Request": "true" } })
      .then(function (response) { return response.text(); })
      .then(function (html) {
        sections.insertAdjacentHTML("afterbegin", html);
        window.htmx.process(sections.firstElementChild);
        contentAdded(sections.firstElementChild);
      });
  }

  document.addEventListener("change", function (event) {
    var input = event.target;
    if (input.matches && input.matches("[data-upload-input]")) {
      enqueue(input.closest("[data-upload-zone]"), input.files);
      input.value = "";
    }
  });

  // Altyazı: dosya adının son parçası dil kodu ya da adıysa (ders.en.srt, ders_turkce.srt) dil seçilir; yoksa varsayılan kalır.

  var LANGUAGE_WORDS = {
    turkce: "tr", turkish: "tr", english: "en", ingilizce: "en", deutsch: "de", german: "de", almanca: "de",
    francais: "fr", french: "fr", fransizca: "fr", espanol: "es", spanish: "es", ispanyolca: "es",
    arabic: "ar", arapca: "ar", russian: "ru", rusca: "ru",
  };

  function guessLanguage(fileName, select) {
    var codes = Array.prototype.map.call(select.options, function (option) { return option.value; });
    var plain = fileName.toLowerCase().replace(/ı/g, "i").normalize("NFD").replace(/[̀-ͯ]/g, "");
    var tokens = plain.replace(SUBTITLE_FILE, "").split(/[^a-z]+/).filter(Boolean);
    var last = tokens[tokens.length - 1] || "";
    var code = codes.indexOf(last) !== -1 ? last : LANGUAGE_WORDS[last];
    return code && codes.indexOf(code) !== -1 ? code : "";
  }

  document.addEventListener("change", function (event) {
    var input = event.target;
    if (!input.matches || !input.matches("[data-subtitle-file]") || !input.files.length) return;
    var select = input.form && input.form.querySelector("[data-subtitle-language]");
    var code = select && guessLanguage(input.files[0].name, select);
    if (code) select.value = code;
  });

  function openSubtitleForm(row, file) {
    var target = document.getElementById(row.id + "-form");
    window.htmx.ajax("GET", row.getAttribute("data-subtitle-url"), { target: target, swap: "innerHTML" }).then(function () {
      var input = target.querySelector("[data-subtitle-file]");
      if (!input) return;
      var transfer = new DataTransfer();
      transfer.items.add(file);
      input.files = transfer.files;
      input.dispatchEvent(new Event("change", { bubbles: true }));
    });
  }

  // Sürükle-bırak hedefleri: video satırı (altyazı), kategori bloğu ve yükleme alanları (video).
  // Hedef dışına bırakılan dosya tarayıcıda açılıp sayfadan çıkılmasın diye her dosya bırakma yakalanır.

  var highlighted = null;

  function hasFiles(event) {
    return event.dataTransfer && Array.prototype.indexOf.call(event.dataTransfer.types, "Files") !== -1;
  }

  function highlight(element) {
    if (highlighted === element) return;
    if (highlighted) highlighted.classList.remove("is-dragover");
    highlighted = element;
    if (element) element.classList.add("is-dragover");
  }

  function dropTarget(event) {
    if (!event.target.closest) return null;
    return event.target.closest("[data-subtitle-drop]") || event.target.closest("[data-upload-zone]");
  }

  document.addEventListener("dragover", function (event) {
    if (!hasFiles(event)) return;
    event.preventDefault();
    highlight(dropTarget(event));
  });

  document.addEventListener("dragleave", function (event) {
    if (!event.relatedTarget) highlight(null);
  });

  document.addEventListener("drop", function (event) {
    if (!hasFiles(event)) return;
    event.preventDefault();
    highlight(null);
    var files = Array.prototype.slice.call(event.dataTransfer.files);
    var row = event.target.closest && event.target.closest("[data-subtitle-drop]");
    var subtitle = files.filter(function (file) { return SUBTITLE_FILE.test(file.name); })[0];
    if (row && subtitle) {
      openSubtitleForm(row, subtitle);
      return;
    }
    var zone = event.target.closest && event.target.closest("[data-upload-zone]");
    if (zone) {
      enqueue(zone, files);
    } else if (subtitle) {
      toast("warning", "Altyazıyı eklemek istediğin videonun satırına bırak.");
    }
  });
})();
