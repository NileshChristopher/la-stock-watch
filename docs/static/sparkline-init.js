/**
 * Sparkline — Draws a simple SVG polyline from an array of numbers.
 * No dependencies. ~15 lines of actual logic.
 */
(function () {
  function drawSparkline(svgEl, data, color) {
    if (!svgEl || !data || data.length < 2) return;

    var w = svgEl.clientWidth || 200;
    var h = svgEl.clientHeight || 60;
    var padding = 4;

    var min = Math.min.apply(null, data);
    var max = Math.max.apply(null, data);
    var range = max - min || 1;

    var points = data.map(function (val, i) {
      var x = padding + (i / (data.length - 1)) * (w - padding * 2);
      var y = h - padding - ((val - min) / range) * (h - padding * 2);
      return x.toFixed(1) + "," + y.toFixed(1);
    });

    var polyline = document.createElementNS("http://www.w3.org/2000/svg", "polyline");
    polyline.setAttribute("points", points.join(" "));
    polyline.setAttribute("fill", "none");
    polyline.setAttribute("stroke", color);
    polyline.setAttribute("stroke-width", "2");
    polyline.setAttribute("stroke-linecap", "round");
    polyline.setAttribute("stroke-linejoin", "round");

    svgEl.appendChild(polyline);
  }

  // Render sparklines using data set in the page
  if (typeof gainerData !== "undefined") {
    drawSparkline(
      document.getElementById("sparkline-gainer"),
      gainerData,
      "#2D7A4F"
    );
  }
  if (typeof loserData !== "undefined") {
    drawSparkline(
      document.getElementById("sparkline-loser"),
      loserData,
      "#C0392B"
    );
  }
})();
