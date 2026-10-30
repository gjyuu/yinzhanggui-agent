/* 银掌柜 · 统一动效层
 *
 * 设计原则: 动效不是装饰, 而是把"状态变化"讲清楚 ——
 *   权限分级(黄/红)、执行结果(余额变动)、审计留痕, 都用运动表达出来。
 *
 * 优先级: 若页面加载了 GSAP(web/vendor/gsap.min.js), 自动用 GSAP 时间轴;
 *         否则退回原生 Web Animations API, 效果一致、零依赖。
 * 无障碍: 命中 prefers-reduced-motion 时全部瞬时完成。
 */
(() => {
  const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const G = window.gsap || null;
  const EASE = "cubic-bezier(.22,.61,.36,1)";

  const num = (n) => Number(n).toLocaleString("zh-CN", {
    minimumFractionDigits: 2, maximumFractionDigits: 2,
  });

  /* ---------- 基础: 元素进场 ---------- */
  function enter(el, opts = {}) {
    if (!el) return;
    const o = { y: 8, dur: 0.32, delay: 0, scale: 1, ...opts };
    if (reduce) { el.style.opacity = 1; return; }
    if (G) {
      G.fromTo(el, { opacity: 0, y: o.y, scale: o.scale },
        { opacity: 1, y: 0, scale: 1, duration: o.dur, delay: o.delay, ease: "power2.out" });
      return;
    }
    el.animate(
      [{ opacity: 0, transform: `translateY(${o.y}px) scale(${o.scale})` },
       { opacity: 1, transform: "none" }],
      { duration: o.dur * 1000, delay: o.delay * 1000, easing: EASE, fill: "both" }
    );
  }

  /* ---------- 列表: 逐条错开 ---------- */
  function stagger(els, opts = {}) {
    const o = { y: 10, dur: 0.3, step: 0.05, delay: 0.06, ...opts };
    Array.from(els || []).forEach((el, i) => enter(el, { ...o, delay: o.delay + i * o.step }));
  }

  /* ---------- SVG 连线: 生长 ---------- */
  function drawPath(path, opts = {}) {
    if (!path || reduce) return;
    let len = 0;
    try { len = path.getTotalLength(); } catch (e) { return; }
    if (!len) return;
    const o = { dur: 0.34, delay: 0, ...opts };
    path.style.strokeDasharray = `${len}`;
    path.style.strokeDashoffset = `${len}`;
    if (G) {
      G.to(path, { strokeDashoffset: 0, duration: o.dur, delay: o.delay, ease: "power1.out" });
      return;
    }
    path.animate([{ strokeDashoffset: len }, { strokeDashoffset: 0 }],
      { duration: o.dur * 1000, delay: o.delay * 1000, easing: EASE, fill: "both" });
  }

  /* ---------- 数字滚动: 让"余额变了"看得见 ---------- */
  function countTo(el, from, to, opts = {}) {
    if (!el) return;
    const o = { dur: 0.7, prefix: "¥", ...opts };
    const start = Number(from), end = Number(to);
    if (reduce || !isFinite(start) || start === end) { el.textContent = o.prefix + num(end); return; }
    const t0 = performance.now();
    const ease = (t) => 1 - Math.pow(1 - t, 3);
    (function step(now) {
      const p = Math.min(1, (now - t0) / (o.dur * 1000));
      el.textContent = o.prefix + num(start + (end - start) * ease(p));
      if (p < 1) requestAnimationFrame(step);
      else el.textContent = o.prefix + num(end);
    })(t0);
  }

  /* ---------- 强调: 一次"呼吸" ---------- */
  function pulse(el, ms = 900) {
    if (!el || reduce) return;
    el.classList.remove("flash");
    void el.offsetWidth;                 // 强制重排, 让动画可重播
    el.classList.add("flash");
    setTimeout(() => el.classList.remove("flash"), ms);
  }

  /* ---------- 弹窗 ---------- */
  function modalIn(mask) {
    if (!mask) return;
    const box = mask.querySelector(".modal");
    if (reduce || !box) return;
    if (G) {
      G.fromTo(box, { opacity: 0, y: 14, scale: 0.97 },
        { opacity: 1, y: 0, scale: 1, duration: 0.3, ease: "power3.out" });
      G.fromTo(mask, { opacity: 0 }, { opacity: 1, duration: 0.2 });
      return;
    }
    box.animate([{ opacity: 0, transform: "translateY(14px) scale(.97)" }, { opacity: 1, transform: "none" }],
      { duration: 300, easing: EASE, fill: "both" });
  }

  /* ---------- 进度条 ---------- */
  function progress(el, pct) {
    if (!el) return;
    el.style.width = `${Math.max(0, Math.min(100, pct))}%`;
  }

  window.Motion = { enter, stagger, drawPath, countTo, pulse, modalIn, progress, engine: G ? "gsap" : "waapi" };
})();
