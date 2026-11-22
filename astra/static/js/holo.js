/* ASTRA holographic renderer — tiny dependency-free 3D wireframe engine.
   - #holo-bg       : full-page particle field + floating mechanical objects (parallax on cursor/scroll)
   - [data-holo=core]: hero centerpiece (geodesic core, orbit rings, satellites)
   Honors prefers-reduced-motion and the admin "effects" setting (full | lite | off). */
(function () {
  "use strict";
  const html = document.documentElement;
  const effects = html.dataset.effects || "full";
  const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches || effects === "off";
  const lite = effects === "lite" || (navigator.hardwareConcurrency || 8) <= 4 || window.innerWidth < 700;
  const DPR = Math.min(window.devicePixelRatio || 1, lite ? 1 : 1.5);

  const accent = () => {
    const rgb = getComputedStyle(html).getPropertyValue("--accent-rgb").trim() || "63,224,255";
    const rgb2 = getComputedStyle(html).getPropertyValue("--accent-2-rgb").trim() || "59,130,246";
    return { a: rgb, b: rgb2 };
  };

  /* ---------- geometry ---------- */
  function icosahedron(r = 1) {
    const t = (1 + Math.sqrt(5)) / 2;
    const v = [[-1, t, 0], [1, t, 0], [-1, -t, 0], [1, -t, 0], [0, -1, t], [0, 1, t], [0, -1, -t], [0, 1, -t],
      [t, 0, -1], [t, 0, 1], [-t, 0, -1], [-t, 0, 1]].map((p) => {
      const n = Math.hypot(...p);
      return p.map((c) => (c / n) * r);
    });
    const e = [];
    for (let i = 0; i < v.length; i++)
      for (let j = i + 1; j < v.length; j++) {
        const d = Math.hypot(v[i][0] - v[j][0], v[i][1] - v[j][1], v[i][2] - v[j][2]);
        if (d < r * 1.1) e.push([i, j]);
      }
    return { v, e };
  }

  function octahedron(r = 1) {
    const v = [[r, 0, 0], [-r, 0, 0], [0, r, 0], [0, -r, 0], [0, 0, r], [0, 0, -r]];
    const e = [[0, 2], [0, 3], [0, 4], [0, 5], [1, 2], [1, 3], [1, 4], [1, 5], [2, 4], [4, 3], [3, 5], [5, 2]];
    return { v, e };
  }

  function gear(r = 1, teeth = 14, depth = 0.22) {
    const v = [], e = [];
    const n = teeth * 4;
    for (const z of [-depth / 2, depth / 2]) {
      for (let i = 0; i < n; i++) {
        const a = (i / n) * Math.PI * 2;
        const rr = i % 4 < 2 ? r : r * 0.84;
        v.push([Math.cos(a) * rr, Math.sin(a) * rr, z]);
      }
      for (let i = 0; i < 24; i++) {
        const a = (i / 24) * Math.PI * 2;
        v.push([Math.cos(a) * r * 0.34, Math.sin(a) * r * 0.34, z]);
      }
    }
    const layer = n + 24;
    for (let L = 0; L < 2; L++) {
      const o = L * layer;
      for (let i = 0; i < n; i++) e.push([o + i, o + ((i + 1) % n)]);
      for (let i = 0; i < 24; i++) e.push([o + n + i, o + n + ((i + 1) % 24)]);
      for (let s = 0; s < 6; s++) e.push([o + n + s * 4, o + ((s * n) / 6 + 1) | 0]);
    }
    for (let i = 0; i < n; i += 2) e.push([i, i + layer]);
    return { v, e };
  }

  function torus(R = 1, r = 0.32, U = 18, V = 8) {
    const v = [], e = [];
    for (let i = 0; i < U; i++)
      for (let j = 0; j < V; j++) {
        const u = (i / U) * Math.PI * 2, w = (j / V) * Math.PI * 2;
        v.push([(R + r * Math.cos(w)) * Math.cos(u), (R + r * Math.cos(w)) * Math.sin(u), r * Math.sin(w)]);
        const idx = i * V + j;
        e.push([idx, i * V + ((j + 1) % V)]);
        e.push([idx, ((i + 1) % U) * V + j]);
      }
    return { v, e };
  }

  function globe(r = 1, lat = 7, lon = 12, seg = 36) {
    const v = [], e = [];
    for (let i = 1; i < lat; i++) {
      const phi = (i / lat) * Math.PI;
      const start = v.length;
      for (let k = 0; k < seg; k++) {
        const th = (k / seg) * Math.PI * 2;
        v.push([r * Math.sin(phi) * Math.cos(th), r * Math.cos(phi), r * Math.sin(phi) * Math.sin(th)]);
        e.push([start + k, start + ((k + 1) % seg)]);
      }
    }
    for (let j = 0; j < lon; j++) {
      const th = (j / lon) * Math.PI * 2;
      const start = v.length;
      for (let k = 0; k <= seg / 2; k++) {
        const phi = (k / (seg / 2)) * Math.PI;
        v.push([r * Math.sin(phi) * Math.cos(th), r * Math.cos(phi), r * Math.sin(phi) * Math.sin(th)]);
        if (k > 0) e.push([start + k - 1, start + k]);
      }
    }
    return { v, e };
  }

  function ring(r = 1, seg = 90) {
    const v = [], e = [];
    for (let k = 0; k < seg; k++) {
      const a = (k / seg) * Math.PI * 2;
      v.push([Math.cos(a) * r, Math.sin(a) * r, 0]);
      e.push([k, (k + 1) % seg]);
    }
    return { v, e };
  }

  /* ---------- math ---------- */
  function rotate(p, rx, ry, rz) {
    let [x, y, z] = p;
    let c = Math.cos(rx), s = Math.sin(rx);
    [y, z] = [y * c - z * s, y * s + z * c];
    c = Math.cos(ry); s = Math.sin(ry);
    [x, z] = [x * c + z * s, -x * s + z * c];
    c = Math.cos(rz); s = Math.sin(rz);
    [x, y] = [x * c - y * s, x * s + y * c];
    return [x, y, z];
  }

  function drawShape(ctx, shape, o, colors) {
    const pts = shape.v.map((p) => {
      const q = rotate([p[0] * o.size, p[1] * o.size, p[2] * o.size], o.rx, o.ry, o.rz);
      const f = 900 / (900 + q[2]);
      return [o.x + q[0] * f, o.y + q[1] * f, q[2]];
    });
    ctx.lineWidth = o.lw || 1;
    ctx.beginPath();
    for (const [i, j] of shape.e) {
      ctx.moveTo(pts[i][0], pts[i][1]);
      ctx.lineTo(pts[j][0], pts[j][1]);
    }
    ctx.strokeStyle = `rgba(${colors},${o.alpha})`;
    ctx.stroke();
    if (o.nodes) {
      ctx.fillStyle = `rgba(${colors},${Math.min(1, o.alpha * 2.2)})`;
      for (const p of pts) {
        const s = p[2] < 0 ? 1.6 : 1;
        ctx.fillRect(p[0] - s / 2, p[1] - s / 2, s, s);
      }
    }
    return pts;
  }

  function setup(canvas) {
    const ctx = canvas.getContext("2d");
    const fit = () => {
      const r = canvas.getBoundingClientRect();
      canvas.width = Math.max(1, r.width * DPR);
      canvas.height = Math.max(1, r.height * DPR);
      ctx.setTransform(DPR, 0, 0, DPR, 0, 0);
    };
    fit();
    return { ctx, fit };
  }

  const pointer = { x: 0, y: 0, tx: 0, ty: 0 };
  window.addEventListener("pointermove", (e) => {
    pointer.tx = e.clientX / window.innerWidth - 0.5;
    pointer.ty = e.clientY / window.innerHeight - 0.5;
  }, { passive: true });

  /* ---------- background field ---------- */
  function background(canvas) {
    const { ctx, fit } = setup(canvas);
    let W = canvas.clientWidth, H = canvas.clientHeight;
    const count = reduced ? 30 : lite ? 35 : 60;
    let parts = [];
    const spawn = () => {
      parts = Array.from({ length: count }, () => ({
        x: Math.random() * W, y: Math.random() * H, z: Math.random(),
        vx: (Math.random() - 0.5) * 0.12, vy: -0.05 - Math.random() * 0.15,
      }));
    };
    const shapes = [
      { s: icosahedron(1), x: 0.86, y: 0.2, size: 70, sp: [0.0016, 0.0023, 0.0007], depth: 0.6, nodes: true },
      { s: gear(1, 16), x: 0.1, y: 0.62, size: 90, sp: [0.0006, 0.0009, 0.0021], depth: 0.35 },
      { s: torus(1, 0.3, 20, 8), x: 0.9, y: 0.78, size: 58, sp: [0.002, 0.0011, 0.0005], depth: 0.8 },
      { s: octahedron(1), x: 0.18, y: 0.14, size: 36, sp: [0.003, 0.002, 0.001], depth: 1, nodes: true },
    ].slice(0, lite ? 2 : 4).map((o) => ({ ...o, rx: Math.random() * 6, ry: Math.random() * 6, rz: 0 }));

    const resize = () => {
      fit();
      W = canvas.clientWidth;
      H = canvas.clientHeight;
      spawn();
    };
    window.addEventListener("resize", resize);
    resize();

    let last = performance.now(), running = true, looping = false;
    const kick = () => {
      if (looping) return;
      looping = true;
      last = performance.now();
      requestAnimationFrame(frame);
    };
    document.addEventListener("visibilitychange", () => {
      running = !document.hidden;
      if (running && !reduced) kick();
    });

    function frame(now) {
      if (!running) { looping = false; return; }
      const dt = Math.min(50, now - last);
      last = now;
      pointer.x += (pointer.tx - pointer.x) * 0.04;
      pointer.y += (pointer.ty - pointer.y) * 0.04;
      const scroll = window.scrollY || 0;
      const col = accent();
      ctx.clearRect(0, 0, W, H);
      ctx.globalCompositeOperation = "lighter";

      for (const p of parts) {
        if (!reduced) {
          p.x += p.vx * dt * (0.4 + p.z);
          p.y += p.vy * dt * (0.4 + p.z);
          if (p.y < -10) { p.y = H + 10; p.x = Math.random() * W; }
          if (p.x < -10) p.x = W + 10;
          if (p.x > W + 10) p.x = -10;
        }
        const px = p.x - pointer.x * 30 * p.z;
        const py = ((p.y - scroll * 0.08 * p.z) % H + H) % H - pointer.y * 30 * p.z;
        const a = 0.15 + p.z * 0.5;
        ctx.fillStyle = `rgba(${col.a},${a})`;
        const s = 0.6 + p.z * 1.3;
        ctx.fillRect(px, py, s, s);
      }

      for (const o of shapes) {
        if (!reduced) {
          o.rx += o.sp[0] * dt;
          o.ry += o.sp[1] * dt;
          o.rz += o.sp[2] * dt;
        }
        const x = o.x * W - pointer.x * 60 * o.depth;
        const y = o.y * H - pointer.y * 60 * o.depth - ((scroll * 0.15 * o.depth) % (H * 1.4));
        const yy = y < -o.size * 2 ? y + H * 1.4 : y;
        drawShape(ctx, o.s, { x, y: yy, size: o.size, rx: o.rx, ry: o.ry, rz: o.rz, alpha: 0.05, lw: 3 }, col.a);
        drawShape(ctx, o.s, { x, y: yy, size: o.size, rx: o.rx, ry: o.ry, rz: o.rz, alpha: 0.22, lw: 0.8, nodes: o.nodes }, col.a);
      }
      ctx.globalCompositeOperation = "source-over";
      if (!reduced) requestAnimationFrame(frame);
      else looping = false;
    }
    kick();
  }

  /* ---------- hero core ---------- */
  function core(canvas) {
    const { ctx, fit } = setup(canvas);
    let W = canvas.clientWidth, H = canvas.clientHeight;
    const g = globe(1, 8, 14, lite ? 28 : 40);
    const ico = icosahedron(1);
    const rings = [ring(1, 120), ring(1, 120), ring(1, 120)];
    const tilts = [[1.2, 0.2, 0], [0.4, 1.1, 0.3], [1.75, -0.5, 0.8]];
    const sats = tilts.map((_, i) => ({ a: i * 2.1, sp: 0.0006 + i * 0.00025 }));
    let t = 0, last = performance.now();
    const resize = () => {
      fit();
      W = canvas.clientWidth;
      H = canvas.clientHeight;
    };
    window.addEventListener("resize", resize);

    let visible = true, looping = false;
    const kick = () => {
      if (looping) return;
      looping = true;
      last = performance.now();
      requestAnimationFrame(frame);
    };
    if ("IntersectionObserver" in window) {
      new IntersectionObserver((en) => {
        visible = en[0].isIntersecting;
        if (visible && !reduced) kick();
      }).observe(canvas);
    }

    function frame(now) {
      if (!visible && !reduced) { looping = false; return; }
      const dt = Math.min(50, now - last);
      last = now;
      if (!reduced) t += dt;
      const col = accent();
      const R = Math.min(W, H) * 0.3;
      const cx = W / 2, cy = H / 2;
      const tiltX = pointer.y * 0.5, tiltY = pointer.x * 0.6;
      ctx.clearRect(0, 0, W, H);

      // ambient glow
      const grad = ctx.createRadialGradient(cx, cy, R * 0.1, cx, cy, R * 1.9);
      grad.addColorStop(0, `rgba(${col.a},0.16)`);
      grad.addColorStop(0.5, `rgba(${col.b},0.05)`);
      grad.addColorStop(1, "rgba(0,0,0,0)");
      ctx.fillStyle = grad;
      ctx.fillRect(0, 0, W, H);
      ctx.globalCompositeOperation = "lighter";

      // HUD tick ring
      ctx.save();
      ctx.translate(cx, cy);
      ctx.rotate(t * 0.00005);
      for (let i = 0; i < 120; i++) {
        const a = (i / 120) * Math.PI * 2;
        const long = i % 10 === 0;
        const r1 = R * 1.62, r2 = R * (long ? 1.72 : 1.67);
        ctx.strokeStyle = `rgba(${col.a},${long ? 0.5 : 0.18})`;
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(Math.cos(a) * r1, Math.sin(a) * r1);
        ctx.lineTo(Math.cos(a) * r2, Math.sin(a) * r2);
        ctx.stroke();
      }
      ctx.strokeStyle = `rgba(${col.a},0.35)`;
      ctx.setLineDash([2, 10]);
      ctx.beginPath();
      ctx.arc(0, 0, R * 1.5, 0, Math.PI * 2);
      ctx.stroke();
      ctx.setLineDash([]);
      ctx.restore();

      // scanning arc
      ctx.save();
      ctx.translate(cx, cy);
      const sweep = (t * 0.0008) % (Math.PI * 2);
      const sg = ctx.createConicGradient ? ctx.createConicGradient(sweep, 0, 0) : null;
      if (sg) {
        sg.addColorStop(0, `rgba(${col.a},0.22)`);
        sg.addColorStop(0.08, `rgba(${col.a},0)`);
        sg.addColorStop(1, `rgba(${col.a},0)`);
        ctx.fillStyle = sg;
        ctx.beginPath();
        ctx.arc(0, 0, R * 1.5, 0, Math.PI * 2);
        ctx.fill();
      }
      ctx.restore();

      const base = { x: cx, y: cy };
      drawShape(ctx, g, { ...base, size: R, rx: 0.35 + tiltX, ry: t * 0.00018 + tiltY, rz: 0.15, alpha: 0.14, lw: 0.8 }, col.a);
      drawShape(ctx, ico, { ...base, size: R * 0.5, rx: -t * 0.0004 + tiltX, ry: -t * 0.0003 + tiltY, rz: t * 0.0002, alpha: 0.5, lw: 1.1, nodes: true }, col.a);
      drawShape(ctx, ico, { ...base, size: R * 0.5, rx: -t * 0.0004 + tiltX, ry: -t * 0.0003 + tiltY, rz: t * 0.0002, alpha: 0.08, lw: 5 }, col.a);

      rings.forEach((rg, i) => {
        const [ax, ay, az] = tilts[i];
        const o = { ...base, size: R * (1.18 + i * 0.12), rx: ax + tiltX, ry: ay + tiltY + t * 0.00007 * (i + 1), rz: az, alpha: 0.3, lw: 0.9 };
        drawShape(ctx, rg, o, i === 1 ? col.b : col.a);
        // satellite
        const s = sats[i];
        if (!reduced) s.a += s.sp * dt * (i % 2 ? -1 : 1);
        const p = rotate([Math.cos(s.a) * o.size, Math.sin(s.a) * o.size, 0], o.rx, o.ry, o.rz);
        const f = 900 / (900 + p[2]);
        const sx = cx + p[0] * f, sy = cy + p[1] * f;
        const glow = ctx.createRadialGradient(sx, sy, 0, sx, sy, 12);
        glow.addColorStop(0, `rgba(${col.a},0.9)`);
        glow.addColorStop(1, `rgba(${col.a},0)`);
        ctx.fillStyle = glow;
        ctx.fillRect(sx - 12, sy - 12, 24, 24);
      });

      // core
      const pulse = 0.75 + Math.sin(t * 0.002) * 0.25;
      const cg = ctx.createRadialGradient(cx, cy, 0, cx, cy, R * 0.28);
      cg.addColorStop(0, `rgba(255,255,255,${0.75 * pulse})`);
      cg.addColorStop(0.3, `rgba(${col.a},${0.55 * pulse})`);
      cg.addColorStop(1, `rgba(${col.a},0)`);
      ctx.fillStyle = cg;
      ctx.beginPath();
      ctx.arc(cx, cy, R * 0.28, 0, Math.PI * 2);
      ctx.fill();
      ctx.globalCompositeOperation = "source-over";
      if (!reduced) requestAnimationFrame(frame);
      else looping = false;
    }
    kick();
  }

  document.addEventListener("DOMContentLoaded", () => {
    const bg = document.getElementById("holo-bg");
    if (bg) background(bg);
    document.querySelectorAll('[data-holo="core"]').forEach(core);
  });
})();
