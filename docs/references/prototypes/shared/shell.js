/* ai_stp multi-page prototype shell: light/dark theme + copy */
(function () {
  var KEY = "ai_stp_proto_theme";

  function isDark() {
    return document.documentElement.classList.contains("dark");
  }

  function applyTheme(theme) {
    var root = document.documentElement;
    root.classList.remove("light", "dark");
    root.classList.add(theme);
    try { localStorage.setItem(KEY, theme); } catch (e) {}
    var dark = theme === "dark";
    document.querySelectorAll("[data-theme-label]").forEach(function (el) {
      el.setAttribute("aria-label", dark ? "Light" : "Dark");
      el.setAttribute("title", dark ? "Light" : "Dark");
    });
    document.querySelectorAll("[data-icon-sun]").forEach(function (el) {
      el.hidden = !dark;
    });
    document.querySelectorAll("[data-icon-moon]").forEach(function (el) {
      el.hidden = dark;
    });
  }

  var saved = null;
  try { saved = localStorage.getItem(KEY); } catch (e) {}
  applyTheme(saved === "dark" || saved === "light" ? saved : "light");

  document.addEventListener("click", function (e) {
    var t = e.target.closest("[data-action]");
    if (!t) return;
    var a = t.getAttribute("data-action");
    if (a === "theme") {
      applyTheme(isDark() ? "light" : "dark");
    } else if (a === "copy") {
      var v = t.getAttribute("data-copy") || "";
      var prev = t.textContent;
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(v).then(function () {
          t.textContent = "Copied";
          setTimeout(function () { t.textContent = prev; }, 1400);
        }).catch(function () {
          t.textContent = "Error";
          setTimeout(function () { t.textContent = prev; }, 1400);
        });
      }
    }
  });
})();
