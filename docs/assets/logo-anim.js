/* Logo-Animation für die AH-Übersicht: Das WoW-Forever-Logo oben setzt sich
   beim Laden aus Splittern zusammen, danach Funken und ein Glanzstreifen,
   der alle paar Sekunden wiederkehrt. Ohne JavaScript bleibt das normale Logo. */
(() => {
  const root = document.documentElement;
  const show = () => root.classList.remove("la");
  const logo = document.querySelector("header.top .logo");
  if (!logo || matchMedia("(prefers-reduced-motion: reduce)").matches) return show();

  const SRC = "assets/img/logos/wow-forever-frei.png";
  const T_DONE = 2.3;                       // Logo vollständig
  const rnd = (a, b) => a + Math.random() * (b - a);
  const clamp = (x, a = 0, b = 1) => Math.max(a, Math.min(b, x));
  const easeOutQuart = t => 1 - Math.pow(1 - t, 4);
  const easeOutCubic = t => 1 - Math.pow(1 - t, 3);

  // Glanzstreifen über dem fertigen Logo (CSS-Maske in Logoform)
  const css = document.createElement("style");
  css.textContent = `
    .logo-w{position:relative;display:inline-block;line-height:0;justify-self:center}
    .logo-w::after{content:"";position:absolute;inset:0;pointer-events:none;opacity:0;
      -webkit-mask:url(${SRC}) center/100% 100% no-repeat;mask:url(${SRC}) center/100% 100% no-repeat;
      background:linear-gradient(105deg,transparent 42%,rgba(255,252,238,.85) 50%,transparent 58%) no-repeat;
      background-size:300% 100%;mix-blend-mode:screen}
    .logo-w.g::after{opacity:1;animation:logo-glanz 9s ease-in-out infinite}
    @keyframes logo-glanz{0%{background-position:100% 0}14%,100%{background-position:0 0}}
    .logo-fx{position:fixed;inset:0;width:100vw;height:100vh;pointer-events:none;z-index:5}
    @media print{.logo-fx,.logo-w::after{display:none}}`;
  document.head.appendChild(css);
  const wrap = document.createElement("span");
  wrap.className = "logo-w";
  logo.replaceWith(wrap); wrap.appendChild(logo);

  const img = new Image();
  img.onerror = show;
  img.onload = run;
  img.src = SRC;

  function run() {
    const IW = img.naturalWidth, IH = img.naturalHeight;
    let alpha = null, opaque = [];
    try {
      const t = document.createElement("canvas"); t.width = IW; t.height = IH;
      const c = t.getContext("2d"); c.drawImage(img, 0, 0);
      alpha = c.getImageData(0, 0, IW, IH).data;
      for (let i = 0; i < 1500; i++) {
        const x = Math.random() * IW | 0, y = Math.random() * IH | 0;
        if (alpha[(y * IW + x) * 4 + 3] > 200) opaque.push([x, y]);
      }
    } catch (e) { alpha = null; }
    if (!opaque.length) for (let i = 0; i < 300; i++) opaque.push([rnd(.1, .9) * IW, rnd(.1, .9) * IH]);

    // Splitter: Gitter mit Zufallsversatz, je Zelle zwei Dreiecke
    const COLS = 10, ROWS = 8, cw = IW / COLS, ch = IH / ROWS, v = [], shards = [];
    for (let j = 0; j <= ROWS; j++) { v[j] = [];
      for (let i = 0; i <= COLS; i++) v[j][i] = [
        i * cw + (i > 0 && i < COLS ? rnd(-.36, .36) * cw : 0),
        j * ch + (j > 0 && j < ROWS ? rnd(-.36, .36) * ch : 0)]; }
    const cx0 = IW / 2, cy0 = IH / 2, rMax = Math.hypot(cx0, cy0);
    for (let j = 0; j < ROWS; j++) for (let i = 0; i < COLS; i++) {
      const a = v[j][i], b = v[j][i + 1], c = v[j + 1][i + 1], d = v[j + 1][i];
      for (const tri of ((i + j) % 2 ? [[a, b, c], [a, c, d]] : [[a, b, d], [b, c, d]])) {
        const mx = (tri[0][0] + tri[1][0] + tri[2][0]) / 3, my = (tri[0][1] + tri[1][1] + tri[2][1]) / 3;
        const pts = tri.map(([x, y]) => [mx + (x - mx) * 1.05, my + (y - my) * 1.05]);
        const bx = Math.floor(Math.min(...pts.map(p => p[0]))), by = Math.floor(Math.min(...pts.map(p => p[1])));
        const bw = Math.ceil(Math.max(...pts.map(p => p[0]))) - bx + 1, bh = Math.ceil(Math.max(...pts.map(p => p[1]))) - by + 1;
        const cv = document.createElement("canvas"); cv.width = bw; cv.height = bh;
        const g = cv.getContext("2d");
        g.beginPath(); pts.forEach(([x, y], k) => k ? g.lineTo(x - bx, y - by) : g.moveTo(x - bx, y - by));
        g.closePath(); g.clip(); g.drawImage(img, -bx, -by);
        if (alpha) {
          const dd = g.getImageData(0, 0, bw, bh).data; let s = 0;
          for (let k = 3; k < dd.length; k += 16) s += dd[k];
          if (s < 255 * 4) continue;
        }
        const dx = mx - cx0, dy = my - cy0, r = Math.hypot(dx, dy) / rMax;
        const ang = Math.atan2(dy, dx) + rnd(-.6, .6), dist = rnd(.5, 1.1) * IW;
        shards.push({ cv, ox: bx - mx, oy: by - my, tx: mx, ty: my,
          sx: mx + Math.cos(ang) * dist, sy: my + Math.sin(ang) * dist,
          rot: rnd(-3.2, 3.2), sc: Math.random() < .3 ? rnd(1.6, 2.4) : rnd(.3, .9),
          delay: .1 + (1 - r) * .85 + rnd(0, .25), dur: rnd(.8, 1.05) });
      }
    }

    const fx = document.createElement("canvas");
    fx.className = "logo-fx";
    document.body.appendChild(fx);
    const ctx = fx.getContext("2d");
    let sparks = [], done = false, t0 = performance.now();

    function frame(now) {
      const t = (now - t0) / 1000, DPR = Math.min(devicePixelRatio || 1, 2);
      const W = innerWidth, H = innerHeight;
      if (fx.width !== W * DPR || fx.height !== H * DPR) { fx.width = W * DPR; fx.height = H * DPR; }
      ctx.setTransform(DPR, 0, 0, DPR, 0, 0);
      ctx.clearRect(0, 0, W, H);
      const R = logo.getBoundingClientRect(), k = R.height / IH;

      if (t < T_DONE) {
        for (const s of shards) {
          const p = clamp((t - s.delay) / s.dur); if (p <= 0) continue;
          const e = easeOutQuart(p), er = easeOutCubic(p);
          ctx.setTransform(DPR * k, 0, 0, DPR * k, DPR * R.left, DPR * R.top);
          ctx.translate(s.sx + (s.tx - s.sx) * e, s.sy + (s.ty - s.sy) * e);
          ctx.rotate(s.rot * (1 - er));
          const sc = s.sc + (1 - s.sc) * er; ctx.scale(sc, sc);
          ctx.globalAlpha = clamp(p * 3);
          ctx.drawImage(s.cv, s.ox, s.oy);
        }
        ctx.globalAlpha = 1;
        ctx.setTransform(DPR, 0, 0, DPR, 0, 0);
      } else if (!done) {
        done = true;
        root.classList.remove("la");        // echtes Logo einblenden
        for (let i = 0; i < 46; i++) {
          const [ox, oy] = opaque[Math.random() * opaque.length | 0];
          const a = rnd(0, 6.283), sp = rnd(20, 110);
          sparks.push({ x: R.left + ox * k, y: R.top + oy * k, vx: Math.cos(a) * sp, vy: Math.sin(a) * sp - 30,
                        life: rnd(.6, 1.3), age: 0, s: rnd(.7, 1.8), h: rnd(38, 48) });
        }
        setTimeout(() => wrap.classList.add("g"), 150);
      }

      // Funken (Gold, auf hellem Papier sichtbar)
      const dt = 1 / 60;
      for (const s of sparks) {
        s.age += dt; s.vy += 90 * dt; s.x += s.vx * dt; s.y += s.vy * dt; s.vx *= .97; s.vy *= .97;
        const a = 1 - s.age / s.life; if (a <= 0) continue;
        ctx.fillStyle = `hsla(${s.h},80%,${42 + 18 * a}%,${a})`;
        ctx.beginPath(); ctx.arc(s.x, s.y, s.s, 0, 6.283); ctx.fill();
      }
      // kurzer Lichtring beim Einrasten
      const rp = (t - T_DONE) / .6;
      if (rp > 0 && rp < 1) {
        ctx.strokeStyle = `rgba(201,168,90,${.6 * (1 - rp)})`; ctx.lineWidth = 2.5 * (1 - rp) + .5;
        ctx.beginPath();
        ctx.ellipse(R.left + R.width / 2, R.top + R.height / 2, R.width * (.5 + .35 * easeOutCubic(rp)),
                    R.height * (.5 + .35 * easeOutCubic(rp)), 0, 0, 6.283);
        ctx.stroke();
      }
      sparks = sparks.filter(s => s.age < s.life);
      if (done && !sparks.length && rp >= 1) { fx.remove(); return; }
      requestAnimationFrame(frame);
    }
    requestAnimationFrame(frame);
  }
})();
