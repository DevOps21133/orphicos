(function () {
  var modal = document.getElementById("anfrage-modal");
  if (!modal) return;
  var form = document.getElementById("anfrage-form");
  var wrap = modal.querySelector("[data-anfrage-formwrap]");
  var ok = modal.querySelector("[data-anfrage-ok]");
  var errEl = modal.querySelector("[data-anfrage-error]");
  var submit = form ? form.querySelector("[type=submit]") : null;
  var lastFocus = null;

  function showError(msg) {
    if (!errEl) return;
    errEl.hidden = !msg;
    errEl.textContent = msg || "";
  }

  function openModal(e) {
    if (e) e.preventDefault();
    lastFocus = document.activeElement;
    modal.hidden = false;
    document.body.classList.add("anfrage-open");
    if (wrap) wrap.hidden = false;
    if (ok) ok.hidden = true;
    showError("");
    if (form) form.reset();
    var first = modal.querySelector("input:not([type=hidden]):not([tabindex='-1'])");
    if (first) first.focus();
  }

  function closeModal() {
    modal.hidden = true;
    document.body.classList.remove("anfrage-open");
    if (lastFocus && lastFocus.focus) lastFocus.focus();
  }

  document.addEventListener("click", function (e) {
    var a = e.target.closest('a[href="#anfrage"], a[href="#anfrage-modal"], .js-anfrage');
    if (a) openModal(e);
  });

  modal.addEventListener("click", function (e) {
    if (e.target === modal || e.target.hasAttribute("data-anfrage-close")) closeModal();
  });

  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && !modal.hidden) closeModal();
  });

  if (!form) return;

  form.addEventListener("submit", function (e) {
    e.preventDefault();
    showError("");
    if (submit) {
      submit.disabled = true;
      submit.textContent = "Wird gesendet…";
    }
    var data = {};
    new FormData(form).forEach(function (v, k) { data[k] = v; });
    fetch("/api/anfrage", {
      method: "POST",
      headers: { "Content-Type": "application/json", "Accept": "application/json" },
      body: JSON.stringify(data)
    }).then(function (r) {
      return r.json().then(function (j) { return { ok: r.ok && j && j.ok, error: j && j.error }; });
    }).then(function (res) {
      if (!res.ok) {
        showError(res.error || "Senden fehlgeschlagen. Bitte telefonisch versuchen.");
        return;
      }
      if (wrap) wrap.hidden = true;
      if (ok) ok.hidden = false;
      var heading = ok && ok.querySelector("h2");
      if (heading) heading.focus();
    }).catch(function () {
      showError("Keine Verbindung. Bitte später erneut versuchen oder anrufen.");
    }).then(function () {
      if (submit) {
        submit.disabled = false;
        submit.textContent = "Anfrage senden";
      }
    });
  });
})();
