// Page interactions (shared by the EN and DE landing pages). Deferred; the page
// is fully functional and readable without it.

// nav hairline on scroll
var nav = document.getElementById('nav');
if (nav) {
  var onScroll = function(){ nav.classList.toggle('scrolled', window.scrollY > 8); };
  onScroll(); window.addEventListener('scroll', onScroll, {passive:true});
}

// Remember a manual language choice (replaces the former inline onclick handlers,
// so the page needs no 'unsafe-inline' in its Content-Security-Policy).
document.querySelectorAll('[data-set-lang]').forEach(function(a){
  a.addEventListener('click', function(){
    try { localStorage.setItem('orphic_lang', a.getAttribute('data-set-lang')); } catch(e){}
  });
});

// scroll reveals (progressive enhancement — content is visible without JS)
if ('IntersectionObserver' in window) {
  var io = new IntersectionObserver(function(entries){
    entries.forEach(function(e){
      if (e.isIntersecting){ e.target.classList.add('in'); io.unobserve(e.target); }
    });
  }, {threshold:0.14, rootMargin:'0px 0px -6% 0px'});
  document.querySelectorAll('.reveal').forEach(function(el){ io.observe(el); });
} else {
  document.querySelectorAll('.reveal').forEach(function(el){ el.classList.add('in'); });
}

// interactive ship — pointer parallax + 3D tilt + gleam.
// Only on fine-pointer devices that allow motion; touch/reduced-motion keep the static image.
(function () {
  var art = document.querySelector('.stage-art');
  if (!art) return;
  var fine = window.matchMedia('(hover:hover) and (pointer:fine)').matches;
  var still = window.matchMedia('(prefers-reduced-motion:reduce)').matches;
  if (!fine || still) return;
  var raf = 0, nx = 0, ny = 0;
  function apply(){
    raf = 0;
    art.style.setProperty('--tx', nx.toFixed(4));
    art.style.setProperty('--ty', ny.toFixed(4));
    art.style.setProperty('--gx', ((nx + 0.5) * 100).toFixed(2) + '%');
    art.style.setProperty('--gy', ((ny + 0.5) * 100).toFixed(2) + '%');
  }
  art.addEventListener('pointermove', function (e) {
    var r = art.getBoundingClientRect();
    nx = (e.clientX - r.left) / r.width - 0.5;   // -0.5 … 0.5
    ny = (e.clientY - r.top) / r.height - 0.5;
    art.classList.add('tilt');
    if (!raf) raf = requestAnimationFrame(apply);
  }, {passive:true});
  art.addEventListener('pointerleave', function () {
    art.classList.remove('tilt');
    nx = ny = 0;
    if (!raf) raf = requestAnimationFrame(apply);
  });
})();
