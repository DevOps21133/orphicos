(function () {
  function kick(v) {
    v.muted = true;
    v.defaultMuted = true;
    v.playsInline = true;
    v.loop = true;
    v.setAttribute("muted", "");
    v.setAttribute("playsinline", "");
    var p = v.play();
    if (p && p.catch) p.catch(function () {
      setTimeout(function () { v.play().catch(function () {}); }, 250);
    });
  }

  function unmute(v, btn) {
    v.muted = false;
    v.defaultMuted = false;
    v.volume = 1;
    v.play().catch(function () {});
    if (btn) btn.hidden = true;
  }

  document.querySelectorAll("video.hook-video").forEach(function (v) {
    kick(v);
    v.addEventListener("canplay", function () { if (v.paused) kick(v); });
    v.addEventListener("loadeddata", function () { if (v.paused) kick(v); });

    var wrap = v.closest(".hook-wrap") || v.parentElement;
    var btn = wrap ? wrap.querySelector(".hook-unmute") : null;
    if (btn) btn.addEventListener("click", function (e) {
      e.preventDefault();
      e.stopPropagation();
      unmute(v, btn);
    });
    v.addEventListener("volumechange", function () {
      if (!v.muted && btn) btn.hidden = true;
    });

    if ("IntersectionObserver" in window) {
      var io = new IntersectionObserver(function (entries) {
        entries.forEach(function (e) {
          if (e.isIntersecting && v.paused) kick(v);
        });
      }, { threshold: 0.2 });
      io.observe(v);
    }
  });
})();
