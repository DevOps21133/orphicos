(function () {
  document.querySelectorAll("video.hook-video").forEach(function (v) {
    v.muted = false;
    var p = v.play();
    if (p && p.catch) p.catch(function () { /* browser blocked unmuted autoplay; controls stay */ });
  });
})();
