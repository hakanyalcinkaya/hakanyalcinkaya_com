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

  // Tarayıcıdan sunucuya gönderim ilerlemesi; Bunny'ye gönderim ilerlemesini ders satırı kendisi yeniler.
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
    if (!pending && !uploading && !uploadQueue.length && !bulkQueue.length && !bulkBusy) return;
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
  var CONTENT_FILE = /\.(md|markdown|txt|html?)$/i;

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
      if (count) count.textContent = lessons.length + " ders";
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
    refreshSelection();
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
    // Düz listeler (kurslar, paketler, kategoriler...): bırakınca sıra { ids } olarak data-sort-url'e gönderilir.
    within(scope, "[data-sortable-list]:not([data-sortable-ready])").forEach(function (list) {
      list.setAttribute("data-sortable-ready", "");
      window.Sortable.create(list, {
        handle: ".studio-handle",
        draggable: "[data-sort-id]",
        animation: 150,
        onEnd: function (event) {
          if (event.oldIndex === event.newIndex) return;
          var ids = Array.prototype.map.call(list.querySelectorAll("[data-sort-id]"), function (row) {
            return row.getAttribute("data-sort-id");
          });
          fetch(list.getAttribute("data-sort-url"), {
            method: "POST",
            headers: { "Content-Type": "application/json", "X-CSRFToken": csrfToken() },
            body: JSON.stringify({ ids: ids }),
          })
            .then(function (response) {
              if (!response.ok) throw new Error(response.status);
              toast("success", "Sıra kaydedildi.");
            })
            .catch(function () {
              toast("error", "Sıralama kaydedilemedi; sayfa yenileniyor.");
              setTimeout(function () { window.location.reload(); }, 1500);
            });
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

  // Toplu seçim: videolar tek tek ya da kategori kutusuyla seçilir; seçim varken işlem çubuğu görünür.
  // Kısmen seçili kategorinin kutusu ara durumda gösterilir. İşlemden sonra liste yeniden çizilir, seçim sıfırlanır.
  function refreshSelection() {
    var bar = document.querySelector("[data-bulk-bar]");
    if (!bar) return;
    document.querySelectorAll("[data-section-id]").forEach(function (section) {
      var box = section.querySelector("[data-section-check]");
      if (!box) return;
      var checks = section.querySelectorAll("[data-lesson-check]");
      var checked = section.querySelectorAll("[data-lesson-check]:checked").length;
      box.checked = checks.length > 0 && checked === checks.length;
      box.indeterminate = checked > 0 && checked < checks.length;
      box.disabled = checks.length === 0;
    });
    var count = document.querySelectorAll("[data-lesson-check]:checked").length;
    bar.querySelector("[data-bulk-count]").textContent = count;
    bar.classList.toggle("d-none", count === 0);
  }

  document.addEventListener("change", function (event) {
    var sectionBox = event.target.closest("[data-section-check]");
    if (sectionBox) {
      sectionBox.closest("[data-section-id]").querySelectorAll("[data-lesson-check]").forEach(function (box) {
        box.checked = sectionBox.checked;
      });
    }
    if (sectionBox || event.target.closest("[data-lesson-check]")) refreshSelection();
  });

  document.addEventListener("click", function (event) {
    if (!event.target.closest("[data-bulk-clear]")) return;
    document.querySelectorAll("[data-lesson-check]:checked").forEach(function (box) { box.checked = false; });
    refreshSelection();
  });

  // Fazla videolar: seçim sayısı silme düğmesine yazılır; "Tümünü seç" kutusu kısmen seçiliyken ara durumda görünür.
  function refreshOrphanSelection() {
    var list = document.querySelector("[data-orphan-list]");
    if (!list) return;
    var checks = list.querySelectorAll("[data-orphan-check]");
    var count = list.querySelectorAll("[data-orphan-check]:checked").length;
    var all = list.querySelector("[data-orphan-all]");
    var bulk = list.querySelector("[data-orphan-bulk]");
    if (all) {
      all.checked = checks.length > 0 && count === checks.length;
      all.indeterminate = count > 0 && count < checks.length;
    }
    if (bulk) {
      bulk.disabled = count === 0;
      bulk.querySelector("[data-orphan-count]").textContent = count;
    }
  }

  document.addEventListener("change", function (event) {
    var all = event.target.closest("[data-orphan-all]");
    if (all) {
      all.closest("[data-orphan-list]").querySelectorAll("[data-orphan-check]").forEach(function (box) {
        box.checked = all.checked;
      });
    }
    if (all || event.target.closest("[data-orphan-check]")) refreshOrphanSelection();
  });

  function contentAdded(element) {
    initSortables(element);
    renumberAll();
    refreshSelection();
  }

  if (window.htmx) window.htmx.onLoad(contentAdded);
  document.body.addEventListener("htmx:afterSettle", function () {
    renumberAll();
    refreshSelection();
  });

  // Video yükleme: dosyalar adlarına göre sıralanır ve sırayla, tek tek gönderilir; her biri bir ders satırı olur.
  // Ders satırına bırakılan video da aynı sıraya girer, o dersin videosu olur; beklemeden sonraki satıra geçilebilir.

  var uploading = false;

  function queueItem(list, label) {
    var item = document.createElement("li");
    item.innerHTML =
      '<div class="d-flex justify-content-between gap-2"><span class="text-truncate" data-upload-name></span>' +
      '<span class="text-body-secondary text-nowrap" data-upload-state>Bekliyor</span></div>' +
      '<div class="progress studio-progress mt-1" role="progressbar" aria-valuemin="0" aria-valuemax="100"><div class="progress-bar" style="width:0%"></div></div>';
    item.querySelector("[data-upload-name]").textContent = label;
    list.appendChild(item);
    return item;
  }

  // Satıra bırakılan videonun ilerlemesi kategorinin altında değil, o dersin satırında görünür.
  function rowUploadList(row) {
    var list = row.querySelector(":scope > [data-upload-list]");
    if (!list) {
      list = document.createElement("ul");
      list.className = "list-unstyled small mt-2 mb-0 vstack gap-2";
      list.setAttribute("data-upload-list", "");
      list.setAttribute("aria-live", "polite");
      row.insertBefore(list, row.querySelector(":scope > [id$='-form']"));
    }
    return list;
  }

  function removeItem(item) {
    var list = item.parentNode;
    item.remove();
    if (list && !list.children.length && list.closest("[data-lesson-id]")) list.remove();
  }

  function enqueue(zone, fileList) {
    var files = Array.prototype.filter.call(fileList, function (file) { return VIDEO_FILE.test(file.name); });
    var skipped = fileList.length - files.length;
    if (skipped) toast("warning", skipped + " dosya video olmadığı için atlandı.");
    files.sort(function (a, b) { return a.name.localeCompare(b.name, "tr", { numeric: true }); });
    files.forEach(function (file) {
      // Kategorinin kendi listesi; satırlardaki listeler (satıra bırakılan videolar) atlanır.
      var list = zone.querySelector(":scope > [data-upload-list]");
      uploadQueue.push({ url: zone.getAttribute("data-upload-url"), file: file, item: queueItem(list, file.name), place: placeLesson });
    });
    pump();
  }

  function enqueueLesson(row, file) {
    var item = queueItem(rowUploadList(row), file.name);
    uploadQueue.push({ url: row.getAttribute("data-video-url"), file: file, item: item, place: placeVideoCell });
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
      xhr.open("POST", job.url);
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
        job.place(xhr).then(function () {
          removeItem(job.item);
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
  // Video var olan (taslak) derse bağlandıysa o dersin satırı yerinde yenilenir.
  function placeLesson(xhr) {
    var existing = document.getElementById("lesson-" + xhr.getResponseHeader("X-Lesson-Id"));
    if (existing) {
      existing.outerHTML = xhr.responseText;
      var row = document.getElementById("lesson-" + xhr.getResponseHeader("X-Lesson-Id"));
      if (row) window.htmx.process(row);
      renumberAll();
      return Promise.resolve();
    }
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

  // Ders videosu yanıtı yalnız video hücresidir (hx-swap-oob); hücre yerinde değişir ve durumunu kendisi yeniler.
  function placeVideoCell(xhr) {
    var box = document.createElement("div");
    box.innerHTML = xhr.responseText;
    Array.prototype.slice.call(box.children).forEach(function (cell) {
      var existing = cell.id && document.getElementById(cell.id);
      if (!existing) return;
      cell.removeAttribute("hx-swap-oob");
      existing.replaceWith(cell);
      window.htmx.process(cell);
    });
    return Promise.resolve();
  }

  // "Videoyu değiştir" formu dosyayı kendisi göndermez: dosya sıraya girer, form kapanır.
  document.body.addEventListener("htmx:confirm", function (event) {
    var form = event.detail.elt;
    if (!form.matches || !form.matches("[data-upload-queue]")) return;
    var input = form.querySelector('input[type="file"]');
    var row = form.closest("[data-video-url]");
    var file = input && input.files[0];
    // Dosya yoksa ya da video değilse form sunucuya gider, hatayı formda gösterir.
    if (!row || !file || !VIDEO_FILE.test(file.name)) return;
    event.preventDefault();
    enqueueLesson(row, file);
    form.closest('[id$="-form"]').innerHTML = "";
  });

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

  // "Ek içerik" paneli: solda altyazı, sağda ek bilgiler. Alana bırakılan dosya forma konup hemen gönderilir;
  // altyazının dili önce dosya adından seçilir.
  function submitDropped(form, file) {
    var input = form.querySelector('input[type="file"]');
    if (!input) return;
    var transfer = new DataTransfer();
    transfer.items.add(file);
    input.files = transfer.files;
    input.dispatchEvent(new Event("change", { bubbles: true }));
    form.requestSubmit();
  }

  function dropKind(file) {
    if (SUBTITLE_FILE.test(file.name)) return "subtitle";
    if (CONTENT_FILE.test(file.name)) return "content";
    return "";
  }

  // Satırın üstüne bırakılan altyazı ya da ek içerik dosyası: panel açılır, dosya ilgili alana gönderilir.
  function openExtrasPanel(row, file) {
    var target = document.getElementById(row.id + "-form");
    window.htmx.ajax("GET", row.getAttribute("data-subtitle-url"), { target: target, swap: "innerHTML" }).then(function () {
      var form = target.querySelector('[data-extra-drop="' + dropKind(file) + '"]');
      if (form) submitDropped(form, file);
    });
  }

  // Ek bilgileri toplu yükleme: dosyalar sırayla gönderilir, sunucu dosya adından dersi bulur.
  // Her dosyanın sonucu listeye yazılır; eşleşen dersin satırındaki "Ek bilgi" rozeti yenilenir.
  var bulkQueue = [];
  var bulkBusy = false;

  function bulkLine(box, name, status, message, lesson) {
    var icons = { saved: "bi-check-circle text-success-emphasis", skipped: "bi-skip-forward text-body-secondary", error: "bi-x-circle text-danger-emphasis" };
    var item = document.createElement("li");
    item.className = "d-flex gap-2 py-1 border-bottom";
    var icon = document.createElement("i");
    icon.className = "bi " + icons[status];
    icon.setAttribute("aria-hidden", "true");
    var text = document.createElement("span");
    text.className = "min-w-0";
    text.textContent = name + (lesson && lesson !== name.replace(/\.[^.]+$/, "") ? " → " + lesson : "") + " · " + message;
    item.append(icon, text);
    box.querySelector("[data-extra-bulk-list]").prepend(item);
    var counter = box.querySelector('[data-count="' + status + '"]');
    counter.textContent = Number(counter.textContent) + 1;
  }

  function bulkProgress(box) {
    var progress = box.querySelector("[data-extra-bulk-progress]");
    progress.textContent = bulkBusy || bulkQueue.length ? "Gönderiliyor… " + bulkQueue.length + " dosya kaldı" : "Bitti";
  }

  function enqueueBulk(box, fileList) {
    box.querySelector("[data-extra-bulk-summary]").classList.remove("d-none");
    Array.prototype.forEach.call(fileList, function (file) {
      if (CONTENT_FILE.test(file.name)) {
        bulkQueue.push({ box: box, file: file });
      } else {
        bulkLine(box, file.name, "error", "Desteklenmeyen tür; Markdown, TXT ya da HTML olmalı.");
      }
    });
    bulkProgress(box);
    if (!bulkBusy) nextBulk();
  }

  function nextBulk() {
    var job = bulkQueue.shift();
    if (!job) {
      bulkBusy = false;
      return;
    }
    bulkBusy = true;
    bulkProgress(job.box);
    var data = new FormData();
    data.append("file", job.file);
    if (job.box.querySelector("[data-extra-bulk-overwrite]").checked) data.append("overwrite", "on");
    fetch(job.box.getAttribute("data-url"), { method: "POST", body: data, headers: { "X-CSRFToken": csrfToken() } })
      .then(function (response) {
        if (!response.ok) throw new Error("Sunucu hatası (" + response.status + ")");
        return response.json();
      })
      .then(function (result) {
        bulkLine(job.box, job.file.name, result.status, result.message, result.lesson);
        var badge = result.lesson_id && document.getElementById("lesson-" + result.lesson_id + "-extra");
        if (badge && result.badge) {
          badge.outerHTML = result.badge;
          window.htmx.process(document.getElementById("lesson-" + result.lesson_id + "-extra"));
        }
      })
      .catch(function (error) {
        bulkLine(job.box, job.file.name, "error", error.message || "Bağlantı koptu");
      })
      .then(function () {
        bulkBusy = bulkQueue.length > 0;
        bulkProgress(job.box);
        nextBulk();
      });
  }

  document.addEventListener("change", function (event) {
    var input = event.target;
    if (!input.matches || !input.matches("[data-extra-bulk-input]") || !input.files.length) return;
    enqueueBulk(input.closest("[data-extra-bulk]"), input.files);
    input.value = "";
  });

  // Stüdyo penceresi: içerik yüklenince açılır; kaydedilince sunucu "hy:dialog-close" gönderir.
  var dialog = document.getElementById("studio-dialog");
  if (dialog) {
    document.body.addEventListener("htmx:afterSwap", function (event) {
      if (event.detail.target.id === "studio-dialog-body" && event.detail.target.innerHTML.trim() && !dialog.open) {
        dialog.showModal();
        var input = dialog.querySelector("[data-md-input]");
        if (input) input.focus();
      }
    });
    document.body.addEventListener("hy:dialog-close", function () { dialog.close(); });
    dialog.addEventListener("click", function (event) {
      if (event.target === dialog || event.target.closest("[data-dialog-close]")) dialog.close();
    });
    dialog.addEventListener("close", function () { document.getElementById("studio-dialog-body").innerHTML = ""; });
  }

  // Basit Markdown düzenleyici: Yaz / Önizleme sekmeleri ve seçili metni biçimlendiren araç çubuğu.
  document.addEventListener("click", function (event) {
    var tab = event.target.closest("[data-md-tab]");
    if (!tab) return;
    var editor = tab.closest("[data-md-editor]");
    var name = tab.getAttribute("data-md-tab");
    editor.querySelectorAll("[data-md-tab]").forEach(function (item) {
      item.classList.toggle("active", item === tab);
      item.setAttribute("aria-selected", item === tab ? "true" : "false");
    });
    editor.querySelectorAll("[data-md-pane]").forEach(function (pane) {
      pane.hidden = pane.getAttribute("data-md-pane") !== name;
    });
    editor.querySelector("[data-md-toolbar]").classList.toggle("invisible", name !== "write");
  });

  var MD_WRAP = { bold: ["**", "**", "kalın metin"], italic: ["_", "_", "italik metin"], code: ["`", "`", "kod"] };
  var MD_LINE = { h2: "## ", ul: "- ", ol: "1. ", quote: "> " };

  function applyMarkdown(input, action) {
    var start = input.selectionStart;
    var end = input.selectionEnd;
    var value = input.value;
    var selected = value.slice(start, end);
    var rangeStart = start;
    var text;
    var cursorStart;
    var cursorEnd;
    if (MD_WRAP[action]) {
      var wrap = MD_WRAP[action];
      var inner = selected || wrap[2];
      text = wrap[0] + inner + wrap[1];
      cursorStart = start + wrap[0].length;
      cursorEnd = cursorStart + inner.length;
    } else if (MD_LINE[action]) {
      // Seçili her satırın başına eklenir; seçim yoksa imlecin olduğu satıra.
      var lineStart = value.lastIndexOf("\n", start - 1) + 1;
      rangeStart = lineStart;
      selected = value.slice(lineStart, end);
      text = selected.split("\n").map(function (line) { return MD_LINE[action] + line; }).join("\n");
      cursorStart = lineStart;
      cursorEnd = lineStart + text.length;
    } else if (action === "link") {
      var label = selected || "bağlantı metni";
      text = "[" + label + "](https://)";
      cursorStart = start + label.length + 3;
      cursorEnd = cursorStart + 8;
    } else if (action === "codeblock") {
      text = "\n```\n" + (selected || "kod") + "\n```\n";
      cursorStart = start + 5;
      cursorEnd = cursorStart + (selected || "kod").length;
    } else if (action === "hr") {
      text = "\n\n---\n\n";
      cursorStart = cursorEnd = start + text.length;
    } else {
      return;
    }
    input.focus();
    input.setRangeText(text, rangeStart, end, "end");
    input.setSelectionRange(cursorStart, cursorEnd);
  }

  document.addEventListener("click", function (event) {
    var button = event.target.closest("[data-md]");
    if (!button) return;
    var input = button.closest("[data-md-editor]").querySelector("[data-md-input]");
    applyMarkdown(input, button.getAttribute("data-md"));
  });

  // Bülten alanları ({{ ad }} vb.): düğmeye basınca en son yazılan metin alanına (yoksa içeriğe) imleç yerine eklenir.
  var lastPersonalizeField = null;
  document.addEventListener("focusin", function (event) {
    if (event.target.matches && event.target.matches("[data-personalize]")) lastPersonalizeField = event.target;
  });
  document.addEventListener("click", function (event) {
    var button = event.target.closest("[data-insert-text]");
    if (!button) return;
    var input = lastPersonalizeField && document.body.contains(lastPersonalizeField)
      ? lastPersonalizeField
      : document.querySelector("[data-personalize][data-md-input]");
    if (!input) return;
    var text = button.getAttribute("data-insert-text");
    input.focus();
    input.setRangeText(text, input.selectionStart, input.selectionEnd, "end");
    input.dispatchEvent(new Event("input", { bubbles: true }));
  });

  document.addEventListener("keydown", function (event) {
    if (!(event.ctrlKey || event.metaKey) || !event.target.matches || !event.target.matches("[data-md-input]")) return;
    var action = { b: "bold", i: "italic", k: "link" }[event.key.toLowerCase()];
    if (!action) return;
    event.preventDefault();
    applyMarkdown(event.target, action);
  });

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

  // Hedef imlecin altından okunur. Tarayıcının verdiği hedef geride kalabilir: kendini yenileyen video hücresi (her 3 sn)
  // ya da biten yüklemenin kalkan satırı sayfayı oynatınca bırakılan öğe imlecin altındaki değil, eski öğe olur.
  function pointerTarget(event) {
    var found = document.elementFromPoint(event.clientX, event.clientY);
    if (found && found.closest) return found;
    var target = event.target;
    return target && target.isConnected && target.closest ? target : null;
  }

  function dropTarget(event) {
    var target = pointerTarget(event);
    if (!target) return null;
    return (
      target.closest("[data-extra-bulk-zone]") ||
      target.closest("[data-extra-drop]") ||
      target.closest("[data-lesson-id]") ||
      target.closest("[data-upload-zone]")
    );
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
    var target = pointerTarget(event);
    if (!target) return;
    var bulkZone = target.closest("[data-extra-bulk-zone]");
    if (bulkZone) {
      enqueueBulk(bulkZone.closest("[data-extra-bulk]"), files);
      return;
    }
    var extraZone = target.closest("[data-extra-drop]");
    if (extraZone) {
      var kind = extraZone.getAttribute("data-extra-drop");
      var match = files.filter(function (file) { return dropKind(file) === kind; })[0];
      if (match) {
        submitDropped(extraZone, match);
      } else {
        toast("warning", kind === "subtitle" ? "Bu alana SRT ya da VTT dosyası bırak." : "Bu alana Markdown, TXT ya da HTML dosyası bırak.");
      }
      return;
    }
    // Satıra tek video bırakıldıysa o derse gider; birden çok video kategoriye bırakılmış sayılır (ada göre eşleşir).
    var lessonRow = target.closest("[data-lesson-id]");
    var videos = files.filter(function (file) { return VIDEO_FILE.test(file.name); });
    if (lessonRow && videos.length === 1) {
      if (lessonRow.hasAttribute("data-video-url")) {
        enqueueLesson(lessonRow, videos[0]);
      } else {
        // İçerik dersine bırakılan video yeni ders açmaz; önce dersin türü değiştirilmeli.
        toast("warning", "Bu bir içerik dersi; videoyu eklemek için önce türünü Video yap.");
      }
      return;
    }
    var row = target.closest("[data-subtitle-drop]");
    var extra = files.filter(function (file) { return dropKind(file); })[0];
    if (row && extra) {
      openExtrasPanel(row, extra);
      return;
    }
    var zone = target.closest("[data-upload-zone]");
    if (zone) {
      enqueue(zone, files);
    } else if (extra) {
      toast("warning", "Altyazıyı ya da ek içeriği eklemek istediğin videonun satırına bırak.");
    }
  });
})();
