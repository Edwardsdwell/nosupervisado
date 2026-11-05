// Cintas onduladas en canvas. `nivel()` devuelve 0..1 y controla la amplitud (p. ej. volumen del audio).
function strands(cv, nivel, op) {
  op = Object.assign({colores: ["#8b5cf6", "#22d3ee", "#f472b6"], n: 3, amp: .5}, op || {});
  const g = cv.getContext("2d"), quieto = matchMedia("(prefers-reduced-motion:reduce)").matches;
  let W, H, t = 0, nv = 0;
  const ajustar = () => {
    const d = devicePixelRatio || 1;
    W = cv.clientWidth; H = cv.clientHeight;
    cv.width = W * d; cv.height = H * d;
    g.setTransform(d, 0, 0, d, 0, 0);
  };
  ajustar(); addEventListener("resize", ajustar);
  (function bucle() {
    t += .016; nv += (nivel() - nv) * .12;
    g.clearRect(0, 0, W, H);
    g.globalCompositeOperation = "lighter"; g.lineCap = "round";
    op.colores.forEach((c, k) => {
      for (let s = 0; s < op.n; s++) {
        g.beginPath();
        for (let x = 0; x <= W; x += 6) {
          const u = x / W, env = Math.pow(Math.sin(Math.PI * u), 1.5);
          const y = H / 2 + env * H * op.amp * (.12 + nv) *
            (Math.sin(u * 6 + t * (1 + k * .4) + s * .9 + k) * .6 + Math.sin(u * 11 - t * 1.3 + k * 2 + s) * .4);
          x ? g.lineTo(x, y) : g.moveTo(x, y);
        }
        g.strokeStyle = c; g.globalAlpha = .55 - s * .12; g.lineWidth = 2.2 - s * .5;
        g.shadowColor = c; g.shadowBlur = 14; g.stroke();
      }
    });
    g.globalAlpha = 1;
    if (!quieto) requestAnimationFrame(bucle);
  })();
}
