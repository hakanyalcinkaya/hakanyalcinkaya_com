(function () {
  "use strict";

  document.documentElement.classList.add("js");

  var ACC = { indigo: "#6366F1", blue: "#3B82F6", orange: "#F97316", pink: "#EC4899" };
  var ON = { indigo: "#ffffff", blue: "#ffffff", orange: "#0b0b0f", pink: "#0b0b0f" };
  var TH = {
    dark: {
      "--bs-body-bg": "#09090b",
      "--bs-body-bg-rgb": "9,9,11",
      "--bs-tertiary-bg": "#111113",
      "--bs-tertiary-bg-rgb": "17,17,19",
      "--bs-secondary-bg": "#1a1a1e",
      "--bs-secondary-bg-rgb": "26,26,30",
      "--bs-body-color": "#f4f4f5",
      "--bs-body-color-rgb": "244,244,245",
      "--bs-emphasis-color": "#ffffff",
      "--bs-emphasis-color-rgb": "255,255,255",
      "--bs-secondary-color": "#a1a1aa",
      "--bs-tertiary-color": "#8b8b94",
      "--bs-border-color": "rgba(255,255,255,.14)",
      "--bs-border-color-translucent": "rgba(255,255,255,.08)",
      "--bs-form-invalid-color": "#f87171",
      "--bs-form-invalid-border-color": "#f87171",
      "--bs-success": "#4ade80",
      "--bs-box-shadow": "0 24px 48px -28px rgba(0,0,0,.9)"
    },
    light: {
      "--bs-body-bg": "#ffffff",
      "--bs-body-bg-rgb": "255,255,255",
      "--bs-tertiary-bg": "#f7f7f9",
      "--bs-tertiary-bg-rgb": "247,247,249",
      "--bs-secondary-bg": "#eeeef2",
      "--bs-secondary-bg-rgb": "238,238,242",
      "--bs-body-color": "#0a0a0c",
      "--bs-body-color-rgb": "10,10,12",
      "--bs-emphasis-color": "#000000",
      "--bs-emphasis-color-rgb": "0,0,0",
      "--bs-secondary-color": "#4d4d56",
      "--bs-tertiary-color": "#62626b",
      "--bs-border-color": "rgba(10,10,12,.16)",
      "--bs-border-color-translucent": "rgba(10,10,12,.09)",
      "--bs-form-invalid-color": "#c81e1e",
      "--bs-form-invalid-border-color": "#c81e1e",
      "--bs-success": "#15803d",
      "--bs-box-shadow": "0 24px 48px -30px rgba(0,0,0,.22)"
    }
  };

  function rgb(hex) {
    var n = parseInt(hex.slice(1), 16);
    return [(n >> 16) & 255, (n >> 8) & 255, n & 255].join(",");
  }

  function read(key) {
    try {
      return localStorage.getItem(key);
    } catch (e) {
      return null;
    }
  }

  function get() {
    var theme = read("site-theme");
    var accent = read("site-accent");
    return { theme: TH[theme] ? theme : "dark", accent: ACC[accent] ? accent : "indigo" };
  }

  function apply(theme, accent, save) {
    if (!TH[theme]) theme = "dark";
    if (!ACC[accent]) accent = "indigo";
    var root = document.documentElement;
    var values = TH[theme];
    var hex = ACC[accent];
    var mix = theme === "dark" ? "white" : "black";
    var text = theme === "dark"
      ? "color-mix(in oklab, " + hex + " 70%, white)"
      : "color-mix(in oklab, " + hex + " 78%, black)";
    root.setAttribute("data-bs-theme", theme);
    root.style.colorScheme = theme;
    for (var key in values) root.style.setProperty(key, values[key]);
    root.style.setProperty("--bs-primary", hex);
    root.style.setProperty("--bs-primary-rgb", rgb(hex));
    root.style.setProperty("--bs-primary-text-emphasis", text);
    root.style.setProperty("--bs-primary-bg-subtle", "color-mix(in oklab, " + hex + " 14%, transparent)");
    root.style.setProperty("--bs-primary-border-subtle", "color-mix(in oklab, " + hex + " 45%, transparent)");
    root.style.setProperty("--bs-link-color", text);
    root.style.setProperty("--bs-link-hover-color", text);
    root.style.setProperty("--bs-focus-ring-color", "color-mix(in oklab, " + hex + " 35%, transparent)");
    root.style.setProperty("--hy-accent-hover", "color-mix(in oklab, " + hex + " 84%, " + mix + ")");
    root.style.setProperty("--hy-accent-on", ON[accent]);
    if (save) {
      try {
        localStorage.setItem("site-theme", theme);
        localStorage.setItem("site-accent", accent);
      } catch (e) {}
    }
    return { theme: theme, accent: accent };
  }

  window.hyTheme = { get: get, apply: apply };
  var initial = get();
  apply(initial.theme, initial.accent, false);
})();
