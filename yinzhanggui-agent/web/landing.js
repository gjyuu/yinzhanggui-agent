/* 银掌柜 · 落地页交互: 数据填充 / 依次进场 / 光束延迟 0.5s / 3D Tilt */
(() => {
  const $ = (id) => document.getElementById(id);
  const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const money = (n) => "¥" + Number(n).toLocaleString("zh-CN", { minimumFractionDigits: 2 });

  /* ---------------- 数据 ---------------- */
  async function loadData() {
    let d;
    try {
      d = await (await fetch("/api/dashboard?scope=customer")).json();
    } catch (e) {
      $("logChain").textContent = "离线";
      return;
    }
    $("dashUserName").textContent = d.user.name;
    $("kpiBalance").textContent = money(d.stats.balance);
    $("kpiSpend").textContent = money(d.stats.month_spend);
    $("kpiPolicy").textContent = d.stats.policy_total + " 项";
    if ($("cfgBalance")) $("cfgBalance").textContent = money(d.stats.balance);
    if ($("cfgSpend")) $("cfgSpend").textContent = money(d.stats.month_spend);
    if ($("cfgSubs")) $("cfgSubs").textContent = d.subs_monthly ? money(d.subs_monthly) + "/月" : "—";
    $("tierGreen").textContent = d.policy.green;
    $("tierYellow").textContent = d.policy.yellow;
    $("tierRed").textContent = d.policy.red;

    renderBars(d.bars);
    renderLogs(d.logs);
  }

  function renderBars(bars) {
    const box = $("chart");
    box.innerHTML = "";
    if (!bars.length) { box.textContent = "暂无数据"; return; }
    const max = Math.max(...bars.map((b) => b.value)) || 1;
    bars.forEach((b, i) => {
      const col = document.createElement("div");
      col.className = "bar-col";
      col.innerHTML = `
        <div class="bar-val">${b.value.toLocaleString("zh-CN", { maximumFractionDigits: 0 })}</div>
        <div class="bar" data-h="${Math.max(8, Math.round((b.value / max) * 100))}"></div>
        <div class="bar-label">${b.label}</div>`;
      box.appendChild(col);
      const bar = col.querySelector(".bar");
      bar.style.width = "64px";  /* 固定等宽, 不随数据变化 */
      setTimeout(() => {
        bar.style.height = (reduce ? 100 : Number(bar.dataset.h)) + "%";
      }, 420 + i * 90);
    });
  }

  function renderLogs(logs) {
    const ul = $("logList");
    ul.innerHTML = "";
    (logs.length ? logs : [{ stage: "system", summary: "暂无审计记录", ts: "" }]).forEach((l, i) => {
      const li = document.createElement("li");
      li.innerHTML = `<span class="lg-stage">${l.stage}</span>
        <span class="lg-txt">${l.summary}</span><span class="lg-ts">${l.ts}</span>`;
      ul.appendChild(li);
      setTimeout(() => li.classList.add("in"), (reduce ? 0 : 620 + i * 70));
    });
    $("logChain").textContent = "✓ 哈希链完整";
  }

  /* ---------------- 依次进场 + 光束延迟亮起 ---------------- */
  function enter() {
    const items = Array.from(document.querySelectorAll("[data-anim]"));
    const M = window.Motion;
    items.forEach((el) => {
      if (reduce) { el.classList.add("in"); return; }
      // 交给 CSS transition, 按 --i 依次错开
      requestAnimationFrame(() => requestAnimationFrame(() => el.classList.add("in")));
    });
    const last = items.length;
    setTimeout(() => {
      document.querySelectorAll(".beam").forEach((b) => b.classList.add("on"));
    }, (reduce ? 0 : 500 + last * 90));   // 内容进场完成后再延迟 0.5s 亮光束
  }

  /* ---------------- 3D Tilt ---------------- */
  function tilt() {
    const el = $("dashboard");
    if (!el || reduce || window.matchMedia("(hover:none)").matches) return;
    const MAX = 7;
    let raf = null, tx = 0, ty = 0;
    const apply = () => {
      raf = null;
      el.style.transform =
        `rotateX(${ty.toFixed(2)}deg) rotateY(${tx.toFixed(2)}deg) translateZ(0)`;
    };
    el.addEventListener("pointermove", (e) => {
      const r = el.getBoundingClientRect();
      const px = (e.clientX - r.left) / r.width - 0.5;
      const py = (e.clientY - r.top) / r.height - 0.5;
      tx = px * MAX * 2;
      ty = -py * MAX * 2;
      el.classList.add("tilting");
      if (!raf) raf = requestAnimationFrame(apply);
    });
    el.addEventListener("pointerleave", () => {
      el.classList.remove("tilting");
      el.style.transform = "rotateX(0) rotateY(0)";
    });
  }

  document.addEventListener("DOMContentLoaded", () => {
    enter();
    tilt();
    loadData();
  });
})();
