/* Scroll-driven origami hero — the scrollbar is the playhead.
   Frame sequence lives in assets/hero/ (f_001.webp …). Progressive
   enhancement: without JS, with reduced-motion, or before frames arrive,
   the hero is a single-viewport section showing the poster image; the
   copy is always plain HTML. Self-hosted, no external requests (CSP). */
(function () {
  "use strict";

  var sec = document.querySelector(".scrollhero");
  if (!sec) return;

  var canvas = sec.querySelector(".sh-canvas");
  var poster = sec.querySelector(".sh-poster");
  var copy = sec.querySelector(".sh-copy");
  var scrim = sec.querySelector(".sh-scrim");
  var hint = sec.querySelector(".sh-hint");
  var caps = [].slice.call(sec.querySelectorAll(".sh-cap"));

  var reduced = false;
  try { reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches; } catch (e) {}
  if (reduced || !canvas || !canvas.getContext) return;

  var COUNT = parseInt(sec.getAttribute("data-frame-count"), 10) || 0;
  var PATH = sec.getAttribute("data-frame-path") || "assets/hero/f_";
  var PAD = parseInt(sec.getAttribute("data-frame-pad"), 10) || 3;
  var EXT = sec.getAttribute("data-frame-ext") || ".webp";
  if (!COUNT) return;

  var ctx = canvas.getContext("2d");
  var frames = new Array(COUNT);
  var current = -1;
  var target = 0;
  var ticking = false;

  function pad(n) {
    var s = String(n);
    while (s.length < PAD) s = "0" + s;
    return s;
  }
  function src(i) { return PATH + pad(i + 1) + EXT; }

  // The scroll runway: 4 viewports of travel while the visual stays pinned.
  sec.classList.add("sh-active");

  function sizeCanvas() {
    var dpr = Math.min(window.devicePixelRatio || 1, 2);
    var w = sec.clientWidth;
    var h = window.innerHeight;
    canvas.width = Math.round(w * dpr);
    canvas.height = Math.round(h * dpr);
    canvas.style.width = w + "px";
    canvas.style.height = h + "px";
    current = -1; // force redraw at new size
    render();
  }

  function draw(img) {
    var cw = canvas.width, ch = canvas.height;
    var iw = img.naturalWidth, ih = img.naturalHeight;
    if (!iw || !ih) return;
    var s = Math.max(cw / iw, ch / ih);
    var dw = iw * s, dh = ih * s;
    ctx.drawImage(img, (cw - dw) / 2, (ch - dh) / 2, dw, dh);
  }

  // Nearest loaded frame at or below the target, else the first loaded above.
  function bestFrame(i) {
    for (var a = i; a >= 0; a--) if (frames[a] && frames[a]._ok) return a;
    for (var b = i + 1; b < COUNT; b++) if (frames[b] && frames[b]._ok) return b;
    return -1;
  }

  function progress() {
    var rect = sec.getBoundingClientRect();
    var run = sec.offsetHeight - window.innerHeight;
    if (run <= 0) return 0;
    var p = -rect.top / run;
    return p < 0 ? 0 : p > 1 ? 1 : p;
  }

  function fade(p, from, to) {
    // 1 inside [from,to], eased to 0 across a soft edge outside
    var e = 0.06;
    if (p <= from - e || p >= to + e) return 0;
    if (p < from) return (p - (from - e)) / e;
    if (p > to) return ((to + e) - p) / e;
    return 1;
  }

  function render() {
    ticking = false;
    var p = progress();
    target = Math.min(COUNT - 1, Math.round(p * (COUNT - 1)));

    var f = bestFrame(target);
    if (f !== -1 && f !== current) {
      draw(frames[f]);
      current = f;
      if (poster && !poster._hidden) { poster.style.opacity = "0"; poster._hidden = true; }
    }

    // headline block: fully readable at rest, gone by 1/4 of the runway
    if (copy) {
      var o = 1 - Math.min(1, p / 0.22);
      copy.style.opacity = String(o);
      copy.style.transform = "translateY(" + (p * -46) + "px)";
      copy.style.pointerEvents = o < 0.35 ? "none" : "";
      if (scrim) scrim.style.opacity = String(o); // unbleach the art once the copy is gone
    }
    if (hint) hint.style.opacity = String(1 - Math.min(1, p / 0.08));

    for (var i = 0; i < caps.length; i++) {
      var from = parseFloat(caps[i].getAttribute("data-from")) || 0;
      var to = parseFloat(caps[i].getAttribute("data-to")) || 1;
      caps[i].style.opacity = String(fade(p, from, to));
    }
  }

  function onScroll() {
    if (!ticking) { ticking = true; window.requestAnimationFrame(render); }
  }

  // Preload with modest concurrency, in playback order.
  var next = 0, inflight = 0, LANES = 6;
  function pump() {
    while (inflight < LANES && next < COUNT) {
      (function (i) {
        var img = new Image();
        img.decoding = "async";
        img.onload = function () { img._ok = true; inflight--; if (i === target || current === -1) onScroll(); pump(); };
        img.onerror = function () { inflight--; pump(); };
        img.src = src(i);
        frames[i] = img;
      })(next++);
      inflight++;
    }
  }

  window.addEventListener("scroll", onScroll, { passive: true });
  window.addEventListener("resize", sizeCanvas);
  sizeCanvas();
  pump();
})();
