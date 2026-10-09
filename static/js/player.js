// HLS player with a moving watermark. Fullscreen applies to the stage (video +
// watermark), not the <video> itself, so the watermark stays visible.
(function () {
  document.querySelectorAll("[data-hls-player]").forEach(function (wrap) {
    var video = wrap.querySelector("video");
    var mark = wrap.querySelector("[data-watermark]");
    var quality = wrap.querySelector("[data-quality]");
    var fullscreen = wrap.querySelector("[data-fullscreen]");
    var stage = wrap.querySelector("[data-stage]");
    var src = wrap.dataset.src;

    if (window.Hls && window.Hls.isSupported()) {
      var hls = new window.Hls({ capLevelToPlayerSize: true });
      hls.loadSource(src);
      hls.attachMedia(video);
      hls.on(window.Hls.Events.MANIFEST_PARSED, function (_, data) {
        if (!quality || data.levels.length < 2) return;
        data.levels
          .map(function (level, i) { return { i: i, h: level.height }; })
          .sort(function (a, b) { return b.h - a.h; })
          .forEach(function (level) {
            var opt = document.createElement("option");
            opt.value = level.i;
            opt.textContent = level.h + "p";
            quality.appendChild(opt);
          });
        quality.hidden = false;
        quality.addEventListener("change", function () {
          hls.currentLevel = parseInt(quality.value, 10);
        });
      });
      hls.on(window.Hls.Events.ERROR, function (_, data) {
        if (!data.fatal) return;
        if (data.type === window.Hls.ErrorTypes.NETWORK_ERROR) hls.startLoad();
        else if (data.type === window.Hls.ErrorTypes.MEDIA_ERROR) hls.recoverMediaError();
      });
    } else if (video.canPlayType("application/vnd.apple.mpegurl")) {
      video.src = src; // Safari / iOS native HLS
    }

    video.addEventListener("contextmenu", function (e) { e.preventDefault(); });

    if (fullscreen) {
      var canFs = stage.requestFullscreen || stage.webkitRequestFullscreen;
      if (!canFs) fullscreen.hidden = true;
      fullscreen.addEventListener("click", function () {
        if (document.fullscreenElement || document.webkitFullscreenElement) {
          (document.exitFullscreen || document.webkitExitFullscreen).call(document);
        } else {
          canFs.call(stage);
        }
      });
      video.addEventListener("dblclick", function () { fullscreen.click(); });
    }

    function moveMark() {
      mark.style.top = (5 + Math.random() * 75) + "%";
      mark.style.left = (5 + Math.random() * 60) + "%";
    }
    if (mark) { moveMark(); setInterval(moveMark, 7000); }
  });
})();
