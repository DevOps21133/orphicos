(function () {
  var videos = Array.prototype.slice.call(document.querySelectorAll("video.hook-video"));
  if (!videos.length) return;

  function wrapOf(v) {
    return v.closest(".hook-wrap") || v.parentElement;
  }

  function btnOf(v) {
    var w = wrapOf(v);
    return w ? w.querySelector(".hook-unmute") : null;
  }

  function showPrompt(v, on) {
    var w = wrapOf(v);
    var btn = btnOf(v);
    if (w) w.classList.toggle("is-muted", on);
    if (btn) btn.hidden = !on;
  }

  function loud(v) {
    v.muted = false;
    v.defaultMuted = false;
    v.removeAttribute("muted");
    v.volume = 1;
    var p = v.play();
    if (p && p.then) {
      p.then(function () {
        if (!v.muted) showPrompt(v, false);
      }).catch(function () {
        showPrompt(v, true);
      });
    } else if (!v.muted) {
      showPrompt(v, false);
    }
  }

  function quiet(v) {
    v.muted = true;
    v.defaultMuted = true;
    v.setAttribute("muted", "");
    v.playsInline = true;
    v.loop = true;
    v.play().catch(function () {
      setTimeout(function () { v.play().catch(function () {}); }, 250);
    });
    showPrompt(v, true);
  }

  function kick(v) {
    v.playsInline = true;
    v.loop = true;
    v.muted = false;
    v.defaultMuted = false;
    v.removeAttribute("muted");
    v.volume = 1;
    var p = v.play();
    if (p && p.then) {
      p.then(function () {
        if (v.muted) {
          v.muted = false;
          v.removeAttribute("muted");
          var p2 = v.play();
          if (p2 && p2.catch) p2.catch(function () { quiet(v); });
          else if (v.muted) quiet(v);
          else showPrompt(v, false);
        } else {
          showPrompt(v, false);
        }
      }).catch(function () {
        quiet(v);
      });
    } else {
      quiet(v);
    }
  }

  videos.forEach(function (v) {
    kick(v);
    v.addEventListener("canplay", function () { if (v.paused) kick(v); });
    var btn = btnOf(v);
    if (btn) {
      btn.addEventListener("click", function (e) {
        e.preventDefault();
        e.stopPropagation();
        loud(v);
      });
    }
    v.addEventListener("volumechange", function () {
      showPrompt(v, !!v.muted);
    });
  });

  function unlock() {
    videos.forEach(loud);
    document.removeEventListener("pointerdown", unlock, true);
    document.removeEventListener("keydown", unlock, true);
    document.removeEventListener("touchstart", unlock, true);
  }
  document.addEventListener("pointerdown", unlock, true);
  document.addEventListener("keydown", unlock, true);
  document.addEventListener("touchstart", unlock, { capture: true, passive: true });
})();
