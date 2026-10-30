/* 银掌柜 · 银行 AI 智能体 —— 前端交互 */
(() => {
  const $ = (id) => document.getElementById(id);
  const state = {
    sessionId: sessionStorage.getItem("yz_session") || "web-" + Math.random().toString(36).slice(2, 8),
    pendingMfa: null,
    mfaMethod: null,
    plan: null,
    busy: false,
  };
  sessionStorage.setItem("yz_session", state.sessionId);

  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  const TIER_CN = { green: "绿色", yellow: "黄色", red: "红色" };

  /* ---------------- 网络 ---------------- */
  async function api(path, body, method = "POST") {
    const opt = { method, headers: { "Content-Type": "application/json" } };
    if (body !== undefined) opt.body = JSON.stringify(body);
    const res = await fetch(path, opt);
    if (!res.ok) throw new Error(`${path} ${res.status}`);
    return res.json();
  }

  /* ---------------- 消息渲染 ---------------- */
  function bubble(role, html, meta) {
    const wrap = document.createElement("div");
    wrap.className = `msg ${role}`;
    const who = document.createElement("div");
    who.className = "who";
    who.textContent = role === "agent" ? "银" : "我";
    const b = document.createElement("div");
    b.className = "bubble";
    b.innerHTML = html + (meta ? `<div class="meta">${meta}</div>` : "");
    wrap.append(who, b);
    $("messages").appendChild(wrap);
    if (window.Motion) window.Motion.enter(wrap, { y: 10, dur: 0.3 });
    $("messages").scrollTop = $("messages").scrollHeight;
    return b;
  }

  function formatReply(text) {
    let out = esc(text);
    out = out.replace(/\[([^\]]{1,24})\]/g, '<span class="head">$1</span>');
    out = out.replace(/(-?[\d,]+\.\d{2})\s*(元)/g, '<span class="num">$1</span> $2');
    // 收款人是关键业务信息, 单独高亮 (符合银行转账页习惯)
    out = out.replace(/(收款人[:：][^\n]{2,40})/g, '<span class="recipient">$1</span>');
    return out;
  }

  /* 全局风控状态: 三色圆点只亮当前状态 */
  function setStatus(status) {
    const map = { done: "已完成", awaiting_confirm: "待确认", awaiting_mfa: "待强验证", locked: "已锁定" };
    let key = status;
    if (status === "blocked" || status === "locked") key = "awaiting_mfa";
    if (status === "clarify" || status === "idle" || status === "paused" || status === "takeover") key = "";
    $("statusDots").querySelectorAll("i").forEach((i) => i.classList.toggle("on", i.dataset.s === key));
    $("statusText").textContent = map[status] || "就绪";
  }

  function metaPills(payload) {
    const pills = [];
    if (payload.policy) {
      const p = payload.policy;
      pills.push(`<span class="pill ${p.tier}">${esc(p.tier_label)}</span>`);
    }
    if (payload.intent) {
      const conf = Math.round((payload.intent.confidence || 0) * 100);
      const label = conf === 0 ? "未识别" : `${esc(payload.intent.name)} · ${conf}%`;
      pills.push(`<span class="pill blue">意图 ${label}</span>`);
    }
    if (payload.guard_blocked) {
      pills.push(`<span class="pill red">幻觉防护已拦截 ${payload.guard_blocked.length} 项</span>`);
    }
    if (payload.latency_ms) pills.push(`<span class="pill">${payload.latency_ms} ms</span>`);
    return pills.join("");
  }

  /* ---------------- 确认卡 ---------------- */
  function confirmCard(pending, host) {
    const hasRed = pending.some((p) => p.tier === "red");
    const el = document.createElement("div");
    el.className = "card" + (hasRed ? " red" : "");
    const head = hasRed
      ? `🔴 需要确认 + 强验证 · ${pending.length} 个动作`
      : `🟡 需要你确认 · ${pending.length} 个动作`;
    el.innerHTML = `<div class="card-head">${head}</div>` + pending.map((p) => `
      <div class="card-item">
        <div class="ci-title">${esc(p.title)} <span class="pill ${p.tier}">${esc(p.tier_label)}</span></div>
        ${(p.details || []).map((d) => `<div class="kv"><span class="k">${esc(d.label)}</span><span class="v">${esc(d.value)}</span></div>`).join("")}
        <div class="kv"><span class="k">风控判定</span><span class="v">${esc(p.reason)}</span></div>
        ${p.review_flag ? `<div class="kv"><span class="k">提示</span><span class="v" style="color:#d92d20">金额较大, 建议人工复核</span></div>` : ""}
      </div>`).join("") + `
      <div class="card-foot">
        <button class="primary js-approve">确认执行</button>
        <button class="reject js-reject">取消</button>
      </div>`;
    // 合并进 AI 气泡: 待确认动作直接长在消息里, 不另外浮一块
    if (host) {
      host.appendChild(el);
      host.classList.add(hasRed ? "pending-high" : "pending");
    } else {
      $("messages").appendChild(el);
    }
    const M = window.Motion;
    if (M) {
      M.enter(el, { y: 8, dur: 0.3 });
      M.stagger(el.querySelectorAll(".card-item"), { y: 6, step: 0.06, delay: 0.08 });
    }
    $("messages").scrollTop = $("messages").scrollHeight;
    const btnOk = el.querySelector(".js-approve");
    if (btnOk) btnOk.onclick = (e) => { e.preventDefault(); decide("approve"); };
    const btnNo = el.querySelector(".js-reject");
    if (btnNo) btnNo.onclick = (e) => { e.preventDefault(); decide("reject"); };
  }

  async function decide(decision) {
    if (state.busy) return null;
    state.busy = true;
    try {
      const r = await api("/api/confirm", { session_id: state.sessionId, decision });
      bubble("user", decision === "approve" ? "确认执行" : "取消");
      apply(r, true);
      return r;
    } catch (e) {
      bubble("agent", "请求失败, 请重试。");
      return null;
    } finally {
      state.busy = false;
    }
  }

  /* ---------------- 统一应用响应 ---------------- */
  function apply(r, isFollowUp) {
    if (r.session_id) {
      state.sessionId = r.session_id;
      sessionStorage.setItem("yz_session", r.session_id);
    }
    const b = bubble("agent", formatReply(r.reply || "(无回复)"), metaPills(r));
    setStatus(r.status);
    if (r.pending && r.pending.length && r.status === "awaiting_confirm") confirmCard(r.pending, b);
    if (r.status === "awaiting_mfa" && r.mfa) openMfa(r.mfa);
    if (r.plan) renderPlan(r.plan);
    if (r.snapshot) renderSnapshot(r.snapshot);
    if (r.audit) renderAudit(r.audit, r.audit_chain);
    if (r.mode) $("modeLabel").textContent = "理解模式: " + (r.mode === "rule" ? "本地规则引擎" : "LLM + 规则引擎");
    refreshAuditChain();
    return b;
  }

  /* ---------------- 发送 ---------------- */
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

  async function sayAndApply(text) {
    bubble("user", esc(text));
    const r = await api("/api/chat", { session_id: state.sessionId, text });
    apply(r);
    return r;
  }

  async function send(text) {
    text = (text ?? $("input").value).trim();
    if (!text || state.busy) return;
    $("input").value = "";
    state.busy = true;
    try {
      await sayAndApply(text);
    } catch (e) {
      bubble("agent", "后端连接失败, 请确认服务已启动。");
    } finally {
      state.busy = false;
    }
  }

  /* ---------------- 一键演示 ---------------- */
  async function autoMfa() {
    const mfa = state.pendingMfa;
    if (!mfa) return null;
    const sms = (mfa.methods || []).find((m) => m.code === "sms");
    const method = sms ? "sms" : ((mfa.methods || [{}])[0].code || "face");
    const code = method === "sms" ? (mfa.demo_code || "") : "ok";
    const btn = document.querySelector(`.mfa-method[data-method="${method}"]`);
    if (btn) btn.click();                       // 视觉上演示"选中一种验证方式"
    if (method === "sms") $("smsCode").value = code;
    await sleep(1500);
    $("mfaMask").classList.add("hidden");
    const r = await api("/api/mfa/verify", { session_id: state.sessionId, method, code });
    apply(r);
    return r;
  }

  async function runDemo() {
    const btn = $("btnDemo");
    if (state.demoRunning) {
      state.demoStop = true;
      btn.textContent = "正在停止…";
      return;
    }
    state.demoRunning = true;
    state.demoStop = false;
    btn.textContent = "■ 停止演示";
    try {
      $("messages").innerHTML = "";
      $("planWrap").classList.add("hidden");
      $("planEmpty").classList.remove("hidden");
      const r0 = await api(`/api/session/${encodeURIComponent(state.sessionId)}/reset`, {}, "POST");
      if (r0.snapshot) renderSnapshot(r0.snapshot);
      greet();
      const data = await api("/api/demo/script", undefined, "GET");
      const steps = data.steps || [];
      for (let i = 0; i < steps.length; i++) {
        if (state.demoStop) break;
        const s = steps[i];
        $("demoProgress").textContent = `${i + 1}/${steps.length} · ${s.scene}`;
        if (window.Motion) window.Motion.progress($("demoBar"), ((i + 1) / steps.length) * 100);
        await sleep(450);
        const r = await sayAndApply(s.say);
        await sleep(1200);
        if (r && r.status === "awaiting_confirm") {
          const r2 = await decide("approve");
          await sleep(600);
          if (r2 && r2.status === "awaiting_mfa") await autoMfa();
        }
        await sleep(700);
      }
      $("demoProgress").textContent = state.demoStop
        ? "演示已停止"
        : `演示完成 ${steps.length}/${steps.length} 步 · 全部通过`;
    } catch (e) {
      $("demoProgress").textContent = "演示中断: " + e.message;
    } finally {
      state.demoRunning = false;
      state.demoStop = false;
      btn.textContent = "▶ 一键演示";
    }
  }

  /* ---------------- DAG ---------------- */
  function renderPlan(plan) {
    state.plan = plan;
    $("planEmpty").classList.add("hidden");
    $("planWrap").classList.remove("hidden");
    $("planSummary").textContent = plan.summary || plan.intent;

    const nodes = plan.nodes || [];
    if (!nodes.length) { $("dag").innerHTML = ""; return; }

    // 分层: 最长路径法
    const layer = new Map(nodes.map((n) => [n.id, 0]));
    for (let i = 0; i < nodes.length; i++) {
      for (const n of nodes) {
        for (const d of n.deps || []) {
          layer.set(n.id, Math.max(layer.get(n.id), (layer.get(d) ?? 0) + 1));
        }
      }
    }
    const groups = {};
    nodes.forEach((n) => {
      const lv = layer.get(n.id);
      if (!groups[lv]) groups[lv] = [];
      groups[lv].push(n);
    });

    const NW = 136, NH = 50, GX = 46, GY = 16;
    const pos = {};
    let maxX = 0, maxY = 0;
    Object.keys(groups).map(Number).sort((a, b) => a - b).forEach((lv) => {
      groups[lv].forEach((n, i) => {
        const x = 12 + lv * (NW + GX);
        const y = 14 + i * (NH + GY);
        pos[n.id] = { x, y };
        maxX = Math.max(maxX, x + NW);
        maxY = Math.max(maxY, y + NH);
      });
    });

    const svg = $("dag");
    svg.setAttribute("viewBox", `0 0 ${maxX + 24} ${maxY + 24}`);
    svg.setAttribute("height", Math.min(maxY + 24, 460));
    svg.innerHTML = "";

    const COLORS = { green: "#33e0a0", yellow: "#f5c04a", red: "#ff6b6b" };
    const FILLS = { green: "rgba(51,224,160,.08)", yellow: "rgba(245,192,74,.08)", red: "rgba(255,107,107,.08)" };
    const mk = (tag, attrs) => {
      const e = document.createElementNS("http://www.w3.org/2000/svg", tag);
      Object.entries(attrs).forEach(([k, v]) => e.setAttribute(k, v));
      return e;
    };

    // 连线
    nodes.forEach((n) => {
      (n.deps || []).forEach((d) => {
        if (!pos[d]) return;
        const a = pos[d], b = pos[n.id];
        const x1 = a.x + NW, y1 = a.y + NH / 2, x2 = b.x, y2 = b.y + NH / 2;
        const mx = (x1 + x2) / 2;
        svg.appendChild(mk("path", {
          d: `M${x1},${y1} C${mx},${y1} ${mx},${y2} ${x2},${y2}`,
          fill: "none", stroke: "rgba(255,255,255,.14)", "stroke-width": "1.5",
        }));
        svg.appendChild(mk("circle", { cx: x2 - 2, cy: y2, r: 2.6, fill: "rgba(255,255,255,.28)" }));
      });
    });

    // 节点
    nodes.forEach((n) => {
      const p = pos[n.id];
      const color = COLORS[n.tier] || "#1f4ed8";
      const done = n.status === "done";
      const failed = n.status === "failed";
      const waiting = n.status === "pending" && n.tier !== "green";

      const g = mk("g", {});
      g.dataset.layer = String(layer.get(n.id) || 0);
      g.appendChild(mk("rect", {
        x: p.x, y: p.y, width: NW, height: NH, rx: 11,
        fill: done ? "rgba(47,123,255,.18)" : (FILLS[n.tier] || "rgba(255,255,255,.04)"),
        stroke: failed ? "#ff6b6b" : color,
        "stroke-width": waiting ? "1.8" : "1.2",
        "stroke-dasharray": waiting ? "5 3" : "0",
      }));
      g.appendChild(mk("circle", { cx: p.x + 14, cy: p.y + NH / 2, r: 4, fill: color }));

      const t1 = mk("text", {
        x: p.x + 26, y: p.y + 21, fill: "#e9eef7", "font-size": "11.5", "font-weight": "600",
      });
      t1.textContent = n.title.length > 9 ? n.title.slice(0, 9) + "…" : n.title;
      g.appendChild(t1);

      const t2 = mk("text", { x: p.x + 26, y: p.y + 37, fill: "#66707f", "font-size": "10" });
      t2.textContent = `${TIER_CN[n.tier] || n.tier} · ${statusCn(n.status)}`;
      g.appendChild(t2);
      svg.appendChild(g);
    });

    // 动效: 节点按层错开出现, 依赖连线逐条生长
    if (window.Motion) {
      svg.querySelectorAll("g").forEach((g) => window.Motion.enter(g, {
        y: 5, dur: 0.3, delay: Number(g.dataset.layer || 0) * 0.09,
      }));
      svg.querySelectorAll("path").forEach((p, i) => window.Motion.drawPath(p, {
        delay: 0.05 + i * 0.03,
      }));
    }
  }

  const statusCn = (s) => ({ done: "已完成", pending: "待执行", failed: "失败", skipped: "跳过", running: "执行中" }[s] || s);

  /* ---------------- 快照 ---------------- */
  function renderSnapshot(snap) {
    if (!snap || !snap.accounts) return;
    state.lastBal = state.lastBal || {};
    $("accounts").innerHTML = snap.accounts.map((a) => {
      const bal = Number(a.balance);
      const prev = state.lastBal[a.id] !== undefined ? state.lastBal[a.id] : bal;
      return `<div class="acc"><span class="k">${esc(a.name)}<em>尾号 ${esc(a.tail)}</em></span>
        <span class="v ${bal < 0 ? "neg" : ""}" data-acc="${esc(a.id)}">${bal < 0 ? "-¥" : "¥"}${Math.abs(bal).toLocaleString("zh-CN", { minimumFractionDigits: 2 })}</span></div>`;
    }).join("");
    // 金额滚动: 让"余额变了多少"看得见
    snap.accounts.forEach((a) => {
      const el = $("accounts").querySelector(`[data-acc="${a.id}"]`);
      const bal = Number(a.balance);
      const prev = state.lastBal[a.id] !== undefined ? state.lastBal[a.id] : bal;
      if (window.Motion && el) {
        window.Motion.countTo(el, Math.abs(prev), Math.abs(bal), { prefix: bal < 0 ? "-¥" : "¥" });
      }
      state.lastBal[a.id] = bal;
    });
  }

  /* ---------------- 审计 ---------------- */
  function renderAudit(items, chain) {
    if (!items) return;
    $("auditList").innerHTML = items.slice().reverse().map((e) => `
      <div class="audit-item ${esc(e.stage)}">
        <div class="st">${esc(e.stage)} · ${esc(e.hash || "")}</div>
        <div class="sm">${esc(e.summary)}</div>
        <div class="ts">${esc((e.ts || "").replace("T", " ").slice(0, 23))}</div>
      </div>`).join("");
    if (chain !== undefined) {
      $("auditChain").textContent = `哈希链 ${chain ? "✓ 完整" : "✗ 异常"}`;
    }
    // 新落盘的审计条目闪一下, 表示"日志是活的"
    const first = $("auditList").firstElementChild;
    if (first && window.Motion) window.Motion.pulse(first, 800);
  }

  async function refreshAuditChain() {
    try {
      const a = await api(`/api/audit?session_id=${encodeURIComponent(state.sessionId)}&limit=60`, undefined, "GET");
      renderAudit(a.items, a.ok);
      if (a.items) $("auditChain").textContent = `哈希链 ${a.ok ? "✓ 完整" : "✗ 异常"} · ${a.chain_length} 条`;
    } catch (e) { /* 忽略 */ }
  }

  /* ---------------- 权限矩阵 ---------------- */
  async function loadPolicy() {
    try {
      const p = await api("/api/policy", undefined, "GET");
      const order = ["green", "yellow", "red"];
      const label = { green: "绿色 · 自动执行", yellow: "黄色 · 用户确认", red: "红色 · 强验证" };
      $("policyTable").innerHTML = order.map((t) => {
        const rows = p.static.filter((r) => r.tier === t);
        return `<div class="tier-block">
          <h4><span class="dot ${t}"></span>${label[t]} <span class="dim small">(${rows.length} 项)</span></h4>
          ${rows.map((r) => `<div class="rule-row"><span class="act">${esc(r.action)}</span>
            <span class="lvl" style="color:${{ green: "#0f9d6e", yellow: "#c2760a", red: "#d92d20" }[t]}">${esc(r.tier)}</span></div>`).join("")}
          ${t === "yellow" ? `<div class="rule-row"><span class="act">transfer ≤ ${p.dynamic.yellow_limit} 元/日累计</span><span class="lvl" style="color:#c2760a">yellow</span></div>` : ""}
          ${t === "red" ? `<div class="rule-row"><span class="act">transfer > ${p.dynamic.yellow_limit} 元/日累计</span><span class="lvl" style="color:#d92d20">red</span></div>` : ""}
        </div>`;
      }).join("");
    } catch (e) { /* 忽略 */ }
  }

  /* ---------------- 强验证 ---------------- */
  function openMfa(mfa) {
    state.pendingMfa = mfa;
    state.mfaMethod = null;
    $("mfaActions").textContent = "待授权动作: " + (mfa.actions || []).join("、");
    $("mfaMethods").innerHTML = (mfa.methods || []).map((m) => `
      <button class="mfa-method" data-method="${esc(m.code)}">
        <span class="ico">${{ face: "🙂", sms: "💬", ushield: "🔑" }[m.code] || "🔒"}</span>
        <span>${esc(m.label)}</span>
      </button>`).join("");
    $("mfaMethods").querySelectorAll(".mfa-method").forEach((btn) => {
      btn.onclick = () => {
        state.mfaMethod = btn.dataset.method;
        $("mfaMethods").querySelectorAll(".mfa-method").forEach((b) => b.classList.remove("sel"));
        btn.classList.add("sel");
        $("smsRow").classList.toggle("hidden", state.mfaMethod !== "sms");
      };
    });
    $("smsRow").classList.add("hidden");
    $("smsCode").value = "";
    $("mfaDemo").textContent = mfa.demo_code
      ? `演示环境: 短信验证码 ${mfa.demo_code} (真实环境走运营商通道, 不回显)`
      : "";
    $("mfaMask").classList.remove("hidden");
    if (window.Motion) window.Motion.modalIn($("mfaMask"));
  }

  async function submitMfa(methodArg, codeArg) {
    if (!state.pendingMfa) return;
    const mArg = typeof methodArg === "string" ? methodArg : null;
    const method = mArg || state.mfaMethod;
    if (!method) { $("mfaDemo").textContent = "请先选择一种验证方式"; return; }
    const cArg = typeof codeArg === "string" ? codeArg : null;
    const code = cArg !== null ? cArg : (method === "sms" ? $("smsCode").value.trim() : "ok");
    $("mfaMask").classList.add("hidden");
    try {
      const r = await api("/api/mfa/verify", { session_id: state.sessionId, method, code });
      apply(r);
    } catch (e) {
      bubble("agent", "验证请求失败。");
    }
  }

  /* ---------------- 安全自检 ---------------- */
  async function runSelfcheck() {
    $("scSummary").textContent = "正在逐项探测…";
    $("scList").innerHTML = "";
    $("scMask").classList.remove("hidden");
    try {
      const r = await api("/api/selfcheck", undefined, "GET");
      $("scSummary").textContent =
        `通过 ${r.passed}/${r.total} 项 · 用时 ${r.elapsed_ms} ms · 权限项: 绿 ${r.policy_summary.green} / 黄 ${r.policy_summary.yellow} / 红 ${r.policy_summary.red}`;
      $("scList").innerHTML = r.cases.map((c) => `
        <div class="sc-item ${c.passed ? "pass" : "fail"}">
          <span class="res">${c.passed ? "通过" : "未过"}</span>
          <div class="body">
            <div class="nm">${esc(c.name)}</div>
            <div class="sm">${esc(c.summary || c.evidence || "")}</div>
            <div class="dm">维度: ${esc(c.dimension)} · 期望: ${esc(c.expect)}</div>
            ${c.raw ? `<details class="sc-raw"><summary>技术详情</summary><pre>${esc(c.raw)}</pre></details>` : ""}
          </div>
        </div>`).join("");
    } catch (e) {
      $("scSummary").textContent = "自检失败: " + e.message;
    }
  }

  /* 全局事件委托: 捕获所有"确认/取消"点击 (含历史遗留的 id 按钮), 并给出即时反馈 */
  document.addEventListener("click", (e) => {
    const ok = e.target.closest(".js-approve, #btnApprove");
    if (ok) {
      e.preventDefault();
      const card = ok.closest(".card");
      if (card) {
        card.querySelectorAll("button").forEach((b) => { b.disabled = true; });
        const tip = document.createElement("div");
        tip.className = "card-tip";
        tip.textContent = "处理中…";
        card.appendChild(tip);
      }
      decide("approve");
      return;
    }
    const no = e.target.closest(".js-reject, #btnReject");
    if (no) {
      e.preventDefault();
      decide("reject");
    }
  });
  /* ---------------- 初始化 ---------------- */
  const CHIPS = [
    "我准备给我爱人买车，我可以拿出多少钱",
    "给王强转 200，备注 饭钱",
    "这个月钱都花哪了",
    "我订了哪些会员",
    "这几款理财产品有什么区别",
    "我爱人生日快到了，帮我安排一下",
  ];

  function boot() {
    $("quickRow").innerHTML = CHIPS.map((c) => `<button class="chip">${esc(c)}</button>`).join("");
    $("quickRow").querySelectorAll(".chip").forEach((b) => {
      b.onclick = () => send(b.textContent);
    });
    $("send").onclick = () => send();
    $("input").addEventListener("keydown", (e) => { if (e.key === "Enter") send(); });
    $("btnSelfcheck").onclick = runSelfcheck;
    // 演示工具默认折叠（客户界面不出现），点一下才展开
    const devToggle = $("devToggle");
    if (devToggle) {
      devToggle.onclick = () => {
        const open = !$("devTools").classList.toggle("hidden");
        devToggle.textContent = open ? "演示工具 ▴" : "演示工具 ▾";
      };
    }
    // 角色视角: 客户只看对话; 风控视角才露出 DAG / 权限矩阵 / 审计日志
    const setView = (v) => {
      const risk = v === "risk";
      // 两个类必须互斥：隐藏右侧面板的规则是 body.view-customer .inspector
      document.body.classList.toggle("view-risk", risk);
      document.body.classList.toggle("view-customer", !risk);
      document.querySelectorAll(".view-btn").forEach((b) => b.classList.toggle("on", b.dataset.view === v));
      localStorage.setItem("yz_view", v);
      if (risk) {
        refreshAuditChain();
        loadPolicy();
      }
    };
    document.querySelectorAll(".view-btn").forEach((b) => {
      b.onclick = () => setView(b.dataset.view);
    });
    // 也支持用 URL 直接进风控视角（录屏/演示方便）
    const urlView = new URLSearchParams(location.search).get("view");
    setView(urlView === "risk" ? "risk" : (localStorage.getItem("yz_view") === "risk" ? "risk" : "customer"));
    // 演示身份 (落地页身份选择器写入): 只影响视角与展示, 不改变账本
    const role = localStorage.getItem("yz_role") || "customer";
    const who = localStorage.getItem("yz_user");
    const lvl = localStorage.getItem("yz_level");
    if (who && $("userName")) $("userName").textContent = who;
    if (lvl && $("userLevel")) $("userLevel").textContent = lvl;
    if (role === "risk") {
      setView("risk");
    }
    $("btnDemo").onclick = runDemo;
    $("scClose").onclick = () => $("scMask").classList.add("hidden");
    $("mfaCancel").onclick = () => {
      $("mfaMask").classList.add("hidden");
      decide("reject");
    };
    $("mfaSubmit").onclick = () => submitMfa();
    $("smsCode").addEventListener("keydown", (e) => { if (e.key === "Enter") submitMfa(); });
    $("btnReset").onclick = async () => {
      const r = await api(`/api/session/${encodeURIComponent(state.sessionId)}/reset`, {}, "POST");
      $("messages").innerHTML = "";
      $("planWrap").classList.add("hidden");
      $("planEmpty").classList.remove("hidden");
      $("demoProgress").textContent = "";
      if (r.snapshot) renderSnapshot(r.snapshot);
      greet();
      refreshAuditChain();
    };
    $("btnAuditRefresh").onclick = refreshAuditChain;
    document.querySelectorAll(".tab").forEach((t) => {
      t.onclick = () => {
        document.querySelectorAll(".tab").forEach((x) => x.classList.remove("active"));
        document.querySelectorAll(".tab-body").forEach((x) => x.classList.remove("active"));
        t.classList.add("active");
        $("tab-" + t.dataset.tab).classList.add("active");
      };
    });
    $("sessionLabel").textContent = "会话 " + state.sessionId.slice(-6) + " · 本地演示环境";
    loadPolicy();
    greet();
    refreshAuditChain();
    api(`/api/session/${encodeURIComponent(state.sessionId)}`, undefined, "GET")
      .then((s) => { if (s.snapshot) renderSnapshot(s.snapshot); if (s.plan) renderPlan(s.plan); })
      .catch(() => {});
  }

  function greet() {
    bubble("agent",
      `<span class="head">我是银掌柜</span>, 你的银行智能体。\n` +
      `可以直接说「给王强转 200 元」「这个月钱都花哪了」「我爱人生日快到了」。\n` +
      `查询类我直接办; 动钱和改状态我会先给你确认卡; 高风险的还要过一道强验证。`,
      `<span class="pill green">绿色自动</span><span class="pill yellow">黄色确认</span><span class="pill red">红色强验证</span>`);
  }

  document.addEventListener("DOMContentLoaded", boot);
})();
