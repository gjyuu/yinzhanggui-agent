/* 个人中心: 真实数据渲染 + 退出登录 */
(() => {
  const $ = (id) => document.getElementById(id);
  const money = (n) => "¥" + Number(n).toLocaleString("zh-CN", { minimumFractionDigits: 2 });

  const who = localStorage.getItem("yz_user") || "张伟";
  const lvl = localStorage.getItem("yz_level") || "金卡客户";
  $("cUserName").textContent = who;
  $("cUserLevel").textContent = lvl;
  $("cAvatar").textContent = who.slice(0, 1);

  $("cLogout").onclick = () => {
    ["yz_user", "yz_level", "yz_role", "yz_view"].forEach((k) => localStorage.removeItem(k));
    location.href = "/";
  };

  async function load() {
    let d;
    try {
      d = await (await fetch("/api/dashboard?scope=customer")).json();
    } catch (e) {
      $("cChart").textContent = "数据加载失败";
      return;
    }
    $("cBalance").textContent = money(d.stats.balance);
    $("cSpend").textContent = money(d.stats.month_spend);
    const total = (d.bars || []).length;
    $("cCount").textContent = (d.logs || []).length ? "实时" : total + " 类支出";
    $("c2Balance").textContent = money(d.stats.balance);
    $("c2Spend").textContent = money(d.stats.month_spend);
    $("cSubs").textContent = d.subs_monthly ? money(d.subs_monthly) + "/月" : "—";
    $("cTierG").textContent = d.policy.green;
    $("cTierY").textContent = d.policy.yellow;
    $("cTierR").textContent = d.policy.red;
    renderBars(d.bars || []);
    renderLogs(d.logs || []);
  }

  function renderBars(bars) {
    const box = $("cChart");
    box.innerHTML = "";
    if (!bars.length) { box.textContent = "暂无数据"; return; }
    const max = Math.max(...bars.map((b) => b.value)) || 1;
    bars.forEach((b, i) => {
      const col = document.createElement("div");
      col.className = "bar-col";
      col.innerHTML = `<div class="bar-val">${b.value.toLocaleString("zh-CN", { maximumFractionDigits: 0 })}</div>
        <div class="bar" data-h="${Math.max(8, Math.round((b.value / max) * 100))}"></div>
        <div class="bar-label">${b.label}</div>`;
      box.appendChild(col);
      const bar = col.querySelector(".bar");
      bar.style.width = "64px";  /* 固定等宽, 不随数据变化 */
      setTimeout(() => { bar.style.height = Number(bar.dataset.h) + "%"; }, 120 + i * 70);
    });
  }

  function renderLogs(logs) {
    const ul = $("cLogList");
    ul.innerHTML = "";
    if (!logs.length) {
      ul.innerHTML = '<li><span class="lg-stage">SYSTEM</span><span class="lg-txt">暂无操作记录, 去控制台说一句话试试</span></li>';
      return;
    }
    logs.slice(0, 6).forEach((l) => {
      const li = document.createElement("li");
      li.innerHTML = `<span class="lg-stage">${l.stage}</span>
        <span class="lg-txt">${l.summary}</span><span class="lg-ts">${l.ts}</span>`;
      ul.appendChild(li);
    });
  }

  load();
})();
