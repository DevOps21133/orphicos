(function () {
  var srcFor = function (id) {
    return "https://www.youtube-nocookie.com/embed/" + id +
      "?rel=0&autoplay=1&mute=0&playsinline=1";
  };

  document.querySelectorAll("[data-yt-sound]").forEach(function (box) {
    box.addEventListener("click", function () {
      if (box.getAttribute("data-yt-on") === "1") return;
      box.setAttribute("data-yt-on", "1");
      var id = box.getAttribute("data-yt-sound");
      var title = box.getAttribute("data-yt-title") || "OrphicOS";
      box.innerHTML =
        '<iframe src="' + srcFor(id) + '" title="' + title.replace(/"/g, "") +
        '" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share"' +
        " allowfullscreen></iframe>";
    });
  });
})();
