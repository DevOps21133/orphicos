/* Head bootstrap (shared by the EN and DE landing pages).
   1) Turns on JS-enhanced styles before first paint (progressive enhancement:
      the page is fully readable with this class absent / JS off).
   2) Routes German-preferring browsers from the English page to the German one.
      No network call. A manual language choice (see app.js) is remembered so
      switching to English never bounces back. Safe on /de/ — it returns early. */
document.documentElement.className = "js";
(function () {
  try {
    if (/^\/de(\/|$)/.test(location.pathname)) return; // already on the German site
    var pref = localStorage.getItem("orphic_lang");
    if (pref === "de") { location.replace("/de/"); return; }
    if (!pref) {
      var lang = (navigator.languages && navigator.languages[0]) || navigator.language || "";
      if (/^de\b/i.test(lang)) { location.replace("/de/"); }
    }
  } catch (e) {}
})();
