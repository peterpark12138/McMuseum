/* ============================================================
   麦麦复活赛 · 老麦返场许愿池
   视觉：设计稿 1:1 还原；数据：全部来自真实 API
   ============================================================ */
const $ = (s, r) => (r || document).querySelector(s);
const $$ = (s, r) => Array.from((r || document).querySelectorAll(s));

const DEADLINE = "2026-10-25T23:59:59+08:00"; // 大赛投票截止（与报名截止同日）

/* 产品真实图：优先取产品数据里的图片档案（七字段，可被 image_research.py 校验），
   HALL_IMG 仅作为历史兜底（迁移期安全网）。无图/加载失败一律走占位卡，绝不留破图。 */
const HALL_IMG = {
  // 麦当劳官方菜单图（menu-img.mcd.cn）
  shake_fries: "assets/products/shake_fries.png",
  purple_sweet_potato_pie: "assets/products/purple_sweet_potato_pie.gif",
  taro_pie: "assets/products/taro_pie.gif",
  big_chicken_steak: "assets/products/big_chicken_steak.png",
  twisty_fries: "assets/products/twisty_fries.png",
  apple_pie: "assets/products/apple_pie.gif",
  shake_fries_fun: "assets/products/shake_fries_fun.png",
  peach_pie: "assets/products/peach_pie.gif",
  mango_pie: "assets/products/mango_pie.gif",
  custard_pie: "assets/products/custard_pie.gif",
  braised_spicy_burger: "assets/products/braised_spicy_burger.png",
  grilled_chicken_burger: "assets/products/grilled_chicken_burger.png",
  // 网络搜集实物照（已逐张核对并白底化）
  sakura_mcfloat: "assets/products/sakura_mcfloat.jpg",
  garlic_chili_sauce: "assets/products/garlic_chili_sauce.jpg",
  mc_rice_wrap: "assets/products/mc_rice_wrap.jpg",
  angus_burger: "assets/products/angus_burger.jpg",
  cilantro_mcfloat: "assets/products/cilantro_mcfloat.jpg",
  youtiao_doujiang: "assets/products/youtiao_doujiang.jpg",
  treasure_triangle: "assets/products/treasure_triangle.jpg",
  strawberry_milkshake: "assets/products/strawberry_milkshake.jpg",
  milkshake: "assets/products/milkshake.jpg",
  veggie_cup: "assets/products/veggie_cup.jpg",
  mccool: "assets/products/mccool.jpg",
  vcut_wedges: "assets/products/vcut_wedges.jpg",
  curry_wing: "assets/products/curry_wing.jpg",
  maple_pancake_burger: "assets/products/maple_pancake_burger.jpg",
  // 设计稿手绘插画（真实设计素材）
  kakazu_crispy_chicken: "assets/v-crispy.png",
  matcha_mcfloat: "assets/v-mcflurry.png",
};

/* 图片加载失败兜底：把 img 换成占位卡。任何失败都不允许影响投票 / 榜单 / 页面其它功能。
   用法：<img ... data-fail-mode="parent|self" data-fallback="🍔" onerror="window.__mcImgFail(this)"> */
window.__mcImgFail = function (el) {
  try {
    const mode = el.getAttribute("data-fail-mode") || "self";
    const fb = el.getAttribute("data-fallback") || "🍔";
    if (mode === "parent") {
      const host = el.parentElement;
      if (host) {
        host.classList.add("emoji");
        host.style.background = "radial-gradient(circle at 40% 30%,#FFF6E5,#FFE9B8)";
        host.style.display = "flex";
        host.style.alignItems = "center";
        host.style.justifyContent = "center";
        host.style.fontSize = "64px";
        host.textContent = fb;
      }
      el.remove();
      return;
    }
    const div = document.createElement("div");
    div.className = ((el.className || "") + " emoji").trim();
    div.textContent = fb;
    el.replaceWith(div);
  } catch (_e) { /* 兜底的兜底：静默失败，不影响主流程 */ }
};

const PODIUM_IMG = {
  taro_pie: "assets/s-taro.png",
  kakazu_crispy_chicken: "assets/s-crispy.png",
};
const MEDALS = ["assets/medal-1st.png", "assets/medal-2nd.png", "assets/medal-3rd.png"];

let PRODUCTS = [];
let PROVINCES = [];
let ACCOUNT = { connected: false, availablePoint: null };
let rankLoaded = false, nowLoaded = false;

/* 在线投票能力（由 /api/vote-capabilities 如实下发）；
   公开部署默认 voting_available=false —— 按钮置灰并引导本机投票，绝不假成功。 */
let VOTE_CAPS = { voting_available: false, mode: "unknown", code: "", msg: "", how_to_vote: "", demo: false };

async function loadVoteCapabilities() {
  try {
    VOTE_CAPS = await (await fetch("/api/vote-capabilities")).json();
  } catch (e) {
    VOTE_CAPS = { voting_available: false, mode: "unknown",
                  msg: "无法获取投票能力状态，按不可用处理。", how_to_vote: "", demo: false };
  }
  renderVoteTip();
  renderDemoBanner();
}

/* 演示模式横幅：全站置顶，任何人一眼能看到"这是演示数据" */
function renderDemoBanner() {
  const bar = $("#demoBanner");
  if (!bar) return;
  if (!VOTE_CAPS.demo) { bar.classList.add("hidden"); return; }
  bar.classList.remove("hidden");
  const txt = $("#demoBannerText");
  if (txt) {
    txt.innerHTML = `<b>演示模式 · 演示数据</b>　页面上的票数是示例值，<b>不是</b>真实投票结果，
      也不会提交到 GitHub 正式共享榜。真实投票需在你本机用麦当劳会员身份完成。`;
  }
}

function renderVoteTip() {
  const tip = $("#voteTip"), txt = $("#voteTipText");
  if (!tip || !txt) return;
  if (VOTE_CAPS.demo) {
    txt.innerHTML = `<b>演示模式：在线投票不可用</b>　这里的票数是示例数据。
      想投出真实的一票，请在本机执行
      <code>python scripts/revival.py vote --product &lt;单品id&gt; --from-mcp</code>，
      或让 WorkBuddy「麦麦复活赛」Skill 代你投票。`;
    tip.classList.remove("hidden");
    return;
  }
  if (VOTE_CAPS.voting_available) { tip.classList.add("hidden"); return; }
  txt.innerHTML = `<b>本站点未开启在线投票</b>：公开服务无法安全验证麦当劳会员身份，也不会代替访客持有会员凭证。
    你可以照常浏览与看榜；真实投票请在本机执行
    <code>python scripts/revival.py vote --product &lt;单品id&gt; --from-mcp</code>，或让 WorkBuddy「麦麦复活赛」Skill 代你投票。`;
  tip.classList.remove("hidden");
}

/* 按钮文案/样式：不可用时显示为不可用态，点击后引导本机流程 */
function voteBtnHtml(pid, isVoted, cls) {
  const can = !!VOTE_CAPS.voting_available;
  const label = isVoted ? "已投" : (can ? "投一票" : (VOTE_CAPS.demo ? "🔒 演示模式" : "🔒 本机投票"));
  const state = isVoted ? "voted" : (can ? "" : "unavailable");
  const title = isVoted ? "" : (can ? "" : "在线投票不可用，点此查看本机投票方式");
  return `<button class="${cls} ${state}" data-pid="${escapeHtml(pid)}" title="${escapeHtml(title)}" onclick="startVote('${escapeHtml(pid)}')">${label}</button>`;
}

/* ---------------- 工具 ---------------- */
function escapeHtml(s) {
  return String(s ?? "").replace(/[&<>"']/g, c => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}
function fmt(n) { return Number(n || 0).toLocaleString("zh-CN"); }

function toast(msg, type) {
  const t = $("#toast");
  t.textContent = msg;
  t.className = "toast" + (type === "err" ? " err" : "");
  clearTimeout(t._h);
  t._h = setTimeout(() => t.classList.add("hidden"), 2600);
}

function iconFor(p) {
  const t = (p.category || "") + (p.name || "") + (p.productName || "");
  if (/蘸酱|酱/.test(t)) return "🥫";
  if (/派/.test(t)) return "🥧";
  if (/麦旋风|冰淇淋|甜筒|雪糕|奶昔/.test(t)) return "🍦";
  if (/咖啡|奶茶|可乐|饮|朱古力/.test(t)) return "🥤";
  if (/薯条|鸡|鸡块|翅|鸡排|小食|丸子/.test(t)) return "🍗";
  if (/卷|饼|馍/.test(t)) return "🌯";
  if (/早餐|粥|麦满分|蛋/.test(t)) return "🍳";
  if (/堡|汉堡/.test(t)) return "🍔";
  if (/饭|面/.test(t)) return "🍚";
  return "🍔";
}

function votedSet() {
  try { return new Set(JSON.parse(sessionStorage.getItem("mcvoted") || "[]")); }
  catch (e) { return new Set(); }
}
function markVoted(pid) {
  const s = votedSet(); s.add(pid);
  sessionStorage.setItem("mcvoted", JSON.stringify([...s]));
}

/* ---------------- 页面切换 ---------------- */
function switchPage(key) {
  $$(".page").forEach(p => p.classList.remove("active"));
  $("#page-" + key).classList.add("active");
  window.scrollTo({ top: 0, behavior: "smooth" });
  if (key === "rank" && !rankLoaded) { rankLoaded = true; loadRank(); }
  if (key === "now" && !nowLoaded) { nowLoaded = true; loadNow(); }
}
$$(".nav a").forEach(a => {
  a.addEventListener("click", e => { e.preventDefault(); switchPage(a.dataset.page); });
});

/* ---------------- 会员状态 ---------------- */
async function loadAccount() {
  try {
    ACCOUNT = await (await fetch("/api/account")).json();
  } catch (e) {
    ACCOUNT = { connected: false, availablePoint: null };
  }
  $$(".acct-pill").forEach(el => {
    el.textContent = ACCOUNT.connected
      ? `可用积分 ${fmt(ACCOUNT.availablePoint)}`
      : "会员未连接";
  });
}

function openMemberModal() {
  const body = $("#modalBody");
  if (ACCOUNT.connected) {
    body.innerHTML = `
      <h3>✅ 麦当劳会员已连接</h3>
      <p>当前可用积分 <b style="color:var(--red)">${fmt(ACCOUNT.availablePoint)}</b>。<br/><br/>
      投票规则：确认会员身份 = <b>1 张基础票</b>；额外票 = <b>积分 ÷ 100</b>（向下取整）。<br/>
      全程只读 MCP：不扣积分、不代下单、不代抽奖。按会员号在本地去重，同一单品只能投一次。</p>
      <button class="confirm-btn" id="modalOk">知道了</button>`;
  } else {
    body.innerHTML = `
      <h3>会员未连接</h3>
      <p>当前部署为<strong>只读展示</strong>：可浏览怀旧单品、查看共享榜与麦麦现在实时数据。
      这里没有、也不会索取你的麦当劳会员凭证。<br/><br/>
      想投出你的复活票：在<b>你自己的本机</b>运行本项目并配置
      <code>MCD_MCP_TOKEN</code>（你自己的麦当劳会员 Token），投票时真实调用
      <code>query-my-account</code> 校验身份，再匿名回流共享榜。</p>
      <div class="cli-box">python scripts/revival.py vote --product &lt;单品id&gt; --from-mcp</div>
      <p style="font-size:12.5px;color:var(--gray-b);margin-top:10px">
      本机想让网页也能投：<code>MCMUSEUM_ENABLE_SERVER_VOTE=1 python web/serve.py</code>。
      详见 <a href="https://github.com/peterpark12138/McMuseum" target="_blank" rel="noopener" style="color:var(--red)">项目 README</a>。</p>
      <button class="confirm-btn" id="modalOk">知道了</button>`;
  }
  $("#modalOk").addEventListener("click", closeModal);
  openModal();
}
$$(".member-btn").forEach(b => b.addEventListener("click", openMemberModal));

/* ---------------- 弹窗 ---------------- */
function openModal() { $("#modal").classList.remove("hidden"); }
function closeModal() { $("#modal").classList.add("hidden"); }
$("#modalClose").addEventListener("click", closeModal);
$("#modal").addEventListener("click", e => { if (e.target.id === "modal") closeModal(); });

/* ---------------- 投票大厅 ---------------- */
async function loadProducts() {
  try {
    PRODUCTS = await (await fetch("/api/products")).json();
  } catch (e) {
    PRODUCTS = [];
  }
  renderHall();
  const total = PRODUCTS.reduce((s, p) => s + (p.votes || 0), 0);
  $("#heroStat").textContent = `已投出 ${fmt(total)} 张复活票 · 候选 ${PRODUCTS.length} 款老味道等你召回`;
}

function renderHall() {
  const q = ($("#searchInput").value || "").trim();
  const sort = $("#hallSort").value;
  const voted = votedSet();
  let list = PRODUCTS.filter(p => !q || p.name.includes(q));
  if (sort === "hot") list = [...list].sort((a, b) => (b.votes || 0) - (a.votes || 0));
  if (sort === "few") list = [...list].sort((a, b) => (a.votes || 0) - (b.votes || 0));
  if (sort === "name") list = [...list].sort((a, b) => a.name.localeCompare(b.name, "zh"));

  const total = PRODUCTS.reduce((s, p) => s + (p.votes || 0), 0);
  const topId = [...PRODUCTS].sort((a, b) => (b.votes || 0) - (a.votes || 0))[0];
  const grid = $("#voteGrid");
  $("#hallEmpty").classList.toggle("hidden", list.length > 0);

  grid.innerHTML = list.map(p => {
    const pct = total ? Math.round((p.votes || 0) / total * 100) : 0;
    const img = p.image || HALL_IMG[p.id];
    const _fb = escapeHtml(iconFor(p));
    const imgHtml = img
      ? `<div class="card-img"><img alt="${escapeHtml(p.name)}" src="${img}" data-fail-mode="parent" data-fallback="${_fb}" onerror="window.__mcImgFail(this)"></div>`
      : `<div class="card-img emoji">${iconFor(p)}</div>`;
    const badge = (topId && topId.id === p.id && (topId.votes || 0) > 0)
      ? "呼声最高"
      : (Array.isArray(p.tags) && p.tags[0]) || p.category || "怀旧单品";
    const isVoted = voted.has(p.id);
    return `<div class="card" data-name="${escapeHtml(p.name)}">
      ${imgHtml}
      <div class="card-name-row"><div class="card-name">${escapeHtml(p.name)}</div><div class="card-badge">${escapeHtml(badge)}</div></div>
      <div class="card-desc" title="${escapeHtml(p.story || "")}">${escapeHtml(p.story || "")}</div>
      <div class="card-votes">
        <div class="row"><span class="num">${fmt(p.votes)} 票</span><span class="pct">占 ${pct}%</span></div>
        <div class="progress"><i style="width:${Math.min(100, pct)}%"></i></div>
      </div>
      ${voteBtnHtml(p.id, isVoted, "vote-btn")}
    </div>`;
  }).join("");
}

$("#searchInput").addEventListener("input", renderHall);
$("#hallSort").addEventListener("change", renderHall);
function refreshHall(btn) {
  btn.classList.remove("spin"); void btn.offsetWidth; btn.classList.add("spin");
  loadProducts();
}

/* ---------------- 投票流程 ---------------- */
let voteTarget = null;

/* 在线投票不可用时的引导弹窗：说清为什么、给出本机做法，不提供"确认投票"按钮 */
function showVoteUnavailable(pid) {
  const p = PRODUCTS.find(x => x.id === pid) || { name: pid };
  const why = escapeHtml(VOTE_CAPS.msg || "本站点未开启在线投票。");
  const how = escapeHtml(VOTE_CAPS.how_to_vote || "");
  const isDemo = !!VOTE_CAPS.demo;
  $("#modalBody").innerHTML = `
    <div class="vote-result">
      <div class="big">${isDemo ? "🧪" : "🔒"}</div>
      <h3>${isDemo ? "演示模式：这里投不了票" : "本站不提供在线投票"}</h3>
      ${isDemo ? `<p style="text-align:left;color:#B4470F;font-size:13px">
        你正在看的是<b>演示数据</b>：示例票数，不是真实投票结果，也不会进入 GitHub 正式共享榜。</p>` : ""}
      <p style="text-align:left">
        浏览怀旧单品与复活榜照常可用；但<b>真实会员投票需要验证「你自己的」麦当劳会员身份</b>，
        公开站点拿不到、也不该保存任何人的会员凭证，所以这里不会假装投票成功。<br/><br/>
        ${why}
      </p>
      <p style="text-align:left;font-weight:900;margin-top:10px">为你投《${escapeHtml(p.name)}》的方式（本机）：</p>
      <div class="cli-box">python scripts/revival.py vote --product ${escapeHtml(pid)} --from-mcp</div>
      <p style="text-align:left;font-size:12.5px;color:var(--gray-b);margin-top:10px">
        ${how ? escapeHtml(how) + "<br/>" : ""}
        或在 WorkBuddy 里让「麦麦复活赛」Skill 代你投票。本机执行后，票数会匿名回流到 GitHub 共享榜。
      </p>
      <button class="confirm-btn" id="modalDone">知道了</button>
    </div>`;
  $("#modalDone").addEventListener("click", closeModal);
  openModal();
}

async function startVote(pid) {
  if (votedSet().has(pid)) return;
  if (!VOTE_CAPS.voting_available) { showVoteUnavailable(pid); return; }
  voteTarget = pid;
  const p = PRODUCTS.find(x => x.id === pid) || { name: pid };
  const opts = PROVINCES.map(pr => `<option value="${escapeHtml(pr)}">${escapeHtml(pr)}</option>`).join("");
  $("#modalBody").innerHTML = `
    <h3>为《${escapeHtml(p.name)}》投一票</h3>
    <p>将以你的麦当劳会员身份确认投票：<br/>
    基础票 <b>1</b> 张 + 积分票（积分 ÷ 100，向下取整）。全程只读 MCP，不扣积分。</p>
    <select id="voteProvince"><option value="">省份（可选，仅统计到省级）</option>${opts}</select>
    <div class="modal-note" id="provinceNote">正在尝试自动识别你的省份…</div>
    <button class="confirm-btn" id="doVote">确认投票</button>
    <div class="modal-note">按会员号在本地去重；同一单品仅能投一次。</div>`;
  openModal();
  $("#doVote").addEventListener("click", doVote);

  // 自动识别省份（仅省级，不取地址）
  try {
    const r = await (await fetch("/api/detect-province")).json();
    const note = $("#provinceNote");
    if (r && r.province && $("#voteProvince")) {
      $("#voteProvince").value = r.province;
      note.textContent = `📍 已自动识别为「${r.province}」，可手动纠正`;
    } else if (note) {
      note.textContent = "未识别到省份，可不选或手动选择（不影响投票）";
    }
  } catch (e) {
    const note = $("#provinceNote");
    if (note) note.textContent = "省份识别不可用，可不选（不影响投票）";
  }
}

async function doVote() {
  const btn = $("#doVote");
  btn.disabled = true; btn.textContent = "投票中…";
  const province = $("#voteProvince").value || null;
  try {
    const res = await fetch("/api/vote", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ product: voteTarget, province }),
    });
    const data = await res.json();
    if (data.ok) {
      markVoted(voteTarget);
      // 诚实回报：本地已计票 ≠ 共享榜已更新，未回流时必须明说
      const shared = data.shared_board_reported;
      $("#modalBody").innerHTML = `
        <div class="vote-result">
          <div class="big">🎉</div>
          <h3>投票成功（本机已计 ${fmt(data.val || 0)} 票）</h3>
          <p style="text-align:left">${escapeHtml(data.msg).replace(/\n/g, "<br/>")}</p>
          ${shared ? "" : `<p style="text-align:left;color:#B4470F;font-size:13px;margin-top:10px">
            ⚠️ 本次投票<b>未</b>回流到 GitHub 共享榜${data.shared_board_msg ? "：" + escapeHtml(data.shared_board_msg) : ""}。
            共享榜只统计成功提交的票，未回流的票只存在于本机 votes.json。</p>`}
          <button class="confirm-btn" id="modalDone">太好了</button>
        </div>`;
      $("#modalDone").addEventListener("click", () => { closeModal(); loadProducts(); });
      $$(`[data-pid="${CSS.escape(voteTarget)}"]`).forEach(b => {
        b.classList.add("voted"); b.textContent = "已投";
      });
      loadAccount();
    } else {
      // 服务端能力不可用（501/503）时不显示"投票没成功"，而是引导本机流程
      const unavail = data.voting_available === false || res.status === 501 || res.status === 503;
      $("#modalBody").innerHTML = `
        <div class="vote-result">
          <div class="big">${unavail ? "🔒" : "🙁"}</div>
          <h3>${unavail ? "本站点不支持在线投票" : "投票没成功"}</h3>
          <p style="text-align:left">${escapeHtml(data.msg || "未知原因")}</p>
          ${data.how_to_vote ? `<div class="cli-box">${escapeHtml(data.how_to_vote)}</div>` : ""}
          <button class="confirm-btn" id="modalDone">知道了</button>
        </div>`;
      $("#modalDone").addEventListener("click", closeModal);
      toast(unavail ? "在线投票不可用，请用本机 CLI / Skill 投票" : "投票未成功，看提示～", "err");
    }
  } catch (e) {
    $("#modalBody").innerHTML = `
      <h3>网络错误</h3>
      <p>无法连接服务，请确认服务运行中。</p>
      <button class="confirm-btn" id="modalDone">关闭</button>`;
    $("#modalDone").addEventListener("click", closeModal);
  }
}

/* ---------------- 复活榜 ---------------- */
async function loadRank() {
  const province = $("#provinceFilter").value;
  const url = "/api/leaderboard" + (province ? `?province=${encodeURIComponent(province)}` : "");
  let d;
  try {
    d = await (await fetch(url)).json();
  } catch (e) {
    $("#rankEmpty").classList.remove("hidden");
    return;
  }
  const items = d.items || [];
  const total = items.reduce((s, x) => s + (x.votes || 0), 0);
  const votedCnt = items.filter(x => (x.votes || 0) > 0).length;

  $("#stTotal").textContent = fmt(total);
  $("#stVoted").textContent = fmt(votedCnt);
  $("#rankUpdated").textContent = "数据更新于 " + new Date().toTimeString().slice(0, 5);
  $("#rankSource").textContent = d.source === "github"
    ? "（GitHub 共享榜 · 匿名票数聚合）"
    : (d.source === "demo"
        ? "（⚠️ 演示数据 · 示例票数，非真实投票结果）"
        : "（本地榜 · " + (d.source || "local") + "）");
  const note = $("#rankNote");
  if (d.fallback && province) {
    note.textContent = `「${province}」暂无投票记录，已为你回退展示全国榜。`;
    note.classList.remove("hidden");
  } else {
    note.classList.add("hidden");
  }

  renderPodium(items, total);
  renderRankRows(items, total);
  $("#rankEmpty").classList.toggle("hidden", items.length > 0);
}

function renderPodium(items, total) {
  const voted = votedSet();
  const top3 = items.slice(0, 3);
  if (!top3.length) { $("#podium").innerHTML = `<div class="state-box">虚位以待，第一票等你来投！</div>`; return; }
  const order = [1, 0, 2].filter(i => i < top3.length); // 2nd, 1st, 3rd
  $("#podium").innerHTML = order.map(i => {
    const it = top3[i];
    const isFirst = i === 0;
    const img = it.image || PODIUM_IMG[it.id] || HALL_IMG[it.id];
    const _pFb = escapeHtml(iconFor(it));
    const prodHtml = img
      ? `<img alt class="rays" src="assets/rays.png"><img alt="${escapeHtml(it.name)}" class="prod" src="${img}" data-fail-mode="self" data-fallback="${_pFb}" onerror="window.__mcImgFail(this)">`
      : `<img alt class="rays" src="assets/rays.png"><div class="prod emoji">${iconFor(it)}</div>`;
    const isVoted = voted.has(it.id);
    return `<div class="top3-card ${isFirst ? "first" : "other"}">
      <div class="medal"><img alt="${i + 1}" src="${MEDALS[i]}"></div>
      <div class="top3-img">${prodHtml}</div>
      <div class="name">${escapeHtml(it.name)}</div>
      <div class="votes">${fmt(it.votes)} 票</div>
      ${voteBtnHtml(it.id, isVoted, "vote-btn")}
    </div>`;
  }).join("");
}

function renderRankRows(items, total) {
  const voted = votedSet();
  const top1 = items.length ? (items[0].votes || 1) : 1;
  const rest = items.slice(3);
  $("#rankList").innerHTML = rest.map((it, idx) => {
    const pct = total ? Math.round((it.votes || 0) / total * 100) : 0;
    const bar = Math.max(2, Math.round((it.votes || 0) / top1 * 100));
    const isVoted = voted.has(it.id);
    return `<div class="rank-row">
      <div class="rank-no">${idx + 4}</div>
      <div class="rank-info"><div class="name">${escapeHtml(it.name)}</div><div class="votes">${fmt(it.votes)} 票 · 占 ${pct}%</div></div>
      <div class="progress"><i style="width:${bar}%"></i></div>
      ${voteBtnHtml(it.id, isVoted, "rank-vote")}
    </div>`;
  }).join("");
}

$("#provinceFilter").addEventListener("change", loadRank);
function refreshRank(btn) {
  btn.classList.remove("spin"); void btn.offsetWidth; btn.classList.add("spin");
  loadRank();
}

/* ---------------- 麦麦现在 ---------------- */
function nowFallback(text) {
  return `<div class="state-box">${escapeHtml(text)}</div>`;
}

async function loadNow() {
  await Promise.allSettled([loadOnSale(), loadCampaigns(), loadMall(), loadLottery(), loadNutrition(), loadNearby()]);
}

async function loadOnSale() {
  const box = $("#availList"), foot = $("#availFoot"), moreBtn = $("#availMore");
  box.innerHTML = `<div class="state-box" style="grid-column:1/-1">在售比对加载中…</div>`;
  moreBtn.classList.add("hidden");
  try {
    const d = await (await fetch("/api/on-sale")).json();
    if (d.fallback) {
      box.innerHTML = `<div style="grid-column:1/-1">${nowFallback("🍔 在售对比需要连接你的麦当劳账号后实时比对。")}</div>`;
      foot.textContent = "";
      return;
    }
    const cmp = d.comparison || {};
    const rows = (PRODUCTS.length ? PRODUCTS : await (await fetch("/api/products")).json())
      .map(p => ({ p, c: cmp[p.id] || { available: false, matched: null } }));
    const COLLAPSED = 10;
    let expanded = false;
    const render = () => {
      const show = expanded ? rows : rows.slice(0, COLLAPSED);
      box.innerHTML = show.map(({ p, c }) => {
        const img = p.image || HALL_IMG[p.id];
        const _aFb = escapeHtml(iconFor(p));
        const imgHtml = img
          ? `<div class="img"><img alt="${escapeHtml(p.name)}" loading="lazy" src="${img}" data-fail-mode="parent" data-fallback="${_aFb}" onerror="window.__mcImgFail(this)"></div>`
          : `<div class="img" style="background:radial-gradient(circle at 40% 30%,#FFF6E5,#FFE9B8)">${iconFor(p)}</div>`;
        return `<div class="avail-card">
          ${imgHtml}
          <div class="name" title="${escapeHtml(p.name)}">${escapeHtml(p.name)}</div>
          ${p.era ? `<div class="era">${escapeHtml(p.era)}</div>` : ""}
          ${c.available
            ? `<div class="tag green" title="仍在售 · ${escapeHtml(c.matched || "")}">仍在售 · ${escapeHtml(c.matched || "")}</div>`
            : `<div class="tag red">已绝版</div>`}
        </div>`;
      }).join("");
      if (rows.length > COLLAPSED) {
        moreBtn.classList.remove("hidden");
        moreBtn.textContent = expanded ? "收起" : `展开更多（共 ${rows.length} 款）`;
      }
    };
    moreBtn.onclick = () => { expanded = !expanded; render(); };
    render();
    foot.textContent = `当前在售餐品共 ${(d.meals || []).length} 款`;
  } catch (e) {
    box.innerHTML = `<div style="grid-column:1/-1">${nowFallback("在售对比加载失败，请确认服务运行中。")}</div>`;
    foot.textContent = "";
  }
}

async function loadCampaigns() {
  const box = $("#campaignGrid");
  box.innerHTML = `<div class="state-box">营销活动加载中…</div>`;
  try {
    const d = await (await fetch("/api/campaigns")).json();
    if (d.fallback || !d.items || !d.items.length) {
      box.innerHTML = nowFallback("📣 营销活动日历需要连接麦当劳账号后实时展示。");
      return;
    }
    box.innerHTML = d.items.slice(0, 10).map(it => `
      <div class="campaign-card">
        ${it.image
          ? `<div class="cover"><img alt="" loading="lazy" src="${escapeHtml(it.image)}"></div>`
          : `<div class="cover" style="background:#FFC72C">${escapeHtml((it.title || "麦麦活动").slice(0, 8))}</div>`}
        <div class="body">
          <div class="t">${escapeHtml(it.title)}</div>
          ${it.date ? `<div class="d">${escapeHtml(it.date)}</div>` : ""}
        </div>
      </div>`).join("");
  } catch (e) {
    box.innerHTML = nowFallback("活动加载失败，请确认服务运行中。");
  }
}

async function loadMall() {
  const box = $("#mallGrid");
  box.innerHTML = `<div class="state-box">积分商城加载中…</div>`;
  try {
    const d = await (await fetch("/api/points-mall")).json();
    if (d.fallback || !d.items || !d.items.length) {
      box.innerHTML = nowFallback("🎁 积分商城需要连接麦当劳账号后实时展示。");
      return;
    }
    box.innerHTML = d.items.slice(0, 8).map(it => `
      <div class="mall-card">
        ${it.image
          ? `<div class="img"><img alt="${escapeHtml(it.spuName)}" loading="lazy" src="${escapeHtml(it.image)}"></div>`
          : `<div class="img" style="background:radial-gradient(circle at 40% 30%,#FFF6E5,#FFE9B8)">🎁</div>`}
        <div class="t" title="${escapeHtml(it.spuName)}">${escapeHtml(it.spuName)}</div>
        ${it.selling ? `<div class="s" title="${escapeHtml(it.selling)}">${escapeHtml(it.selling)}</div>` : ""}
        <div class="pill">${escapeHtml(String(it.point))} 积分</div>
      </div>`).join("");
  } catch (e) {
    box.innerHTML = nowFallback("积分商城加载失败，请确认服务运行中。");
  }
}

async function loadLottery() {
  const box = $("#lotteryWrap");
  box.innerHTML = `<div class="state-box">抽奖信息加载中…</div>`;
  try {
    const d = await (await fetch("/api/lottery")).json();
    if (d.fallback || !d.info || !Object.keys(d.info).length) {
      box.innerHTML = nowFallback("🎰 抽奖信息为你的账号专属数据，连接麦当劳账号后展示。");
      return;
    }
    const info = d.info;
    const prizes = (info.prizes || []).filter(Boolean);
    box.innerHTML = `
      <div class="lottery-card">
        <div class="t">${escapeHtml(info.activityStatusText || "抽奖活动")}</div>
        ${info.cost ? `<div class="c">单次消耗：${escapeHtml(String(info.cost))} 积分</div>` : ""}
        ${prizes.length ? `<div class="p">奖品含：${prizes.map(escapeHtml).join("、")}</div>` : ""}
      </div>`;
  } catch (e) {
    box.innerHTML = nowFallback("抽奖信息加载失败，请确认服务运行中。");
  }
}

async function loadNutrition(name) {
  const box = $("#nutList");
  box.innerHTML = `<div class="state-box">营养数据加载中…</div>`;
  try {
    const url = name ? `/api/nutrition?name=${encodeURIComponent(name)}` : "/api/nutrition";
    const d = await (await fetch(url)).json();
    if (d.fallback || !d.items || !d.items.length) {
      box.innerHTML = nowFallback(name ? "未找到匹配的营养数据，换个关键词试试。" : "🥗 营养库需要连接麦当劳账号后实时展示。");
      return;
    }
    box.innerHTML = d.items.slice(0, 40).map(it => `
      <div class="nut-card" data-name="${escapeHtml(it.productName)}">
        <div class="hd"><span class="ico">${iconFor(it)}</span><div class="t" title="${escapeHtml(it.productName)}">${escapeHtml(it.productName)}</div></div>
        <div class="kcal"><span class="lab">能量</span><span><span class="v">${escapeHtml(it.energyKcal)}</span> <span class="u">kcal</span></span></div>
        <div class="nr"><span class="k">蛋白质</span><span class="val">${escapeHtml(it.protein)} g</span></div>
        <div class="nr"><span class="k">脂肪</span><span class="val">${escapeHtml(it.fat)} g</span></div>
        <div class="nr"><span class="k">碳水化合物</span><span class="val">${escapeHtml(it.carbohydrate)} g</span></div>
      </div>`).join("");
  } catch (e) {
    box.innerHTML = nowFallback("营养库加载失败，请确认服务运行中。");
  }
}
$("#nutBtn").addEventListener("click", () => loadNutrition($("#nutInput").value.trim()));
$("#nutInput").addEventListener("keydown", e => { if (e.key === "Enter") loadNutrition($("#nutInput").value.trim()); });

async function loadNearby() {
  const box = $("#nearbyWrap");
  box.innerHTML = `<div class="state-box">门店信息加载中…</div>`;
  try {
    const d = await (await fetch("/api/nearby")).json();
    if (d.fallback || !d.stores || !d.stores.length) {
      box.innerHTML = nowFallback("📍 附近门店为你的账号专属数据，连接麦当劳账号后展示（仅取省级，不保存地址）。");
      return;
    }
    box.innerHTML = `
      ${d.province ? `<div class="store-prov">已识别省份：${escapeHtml(d.province)}（仅省级，未保存地址）</div>` : ""}
      <div class="store-list" style="margin-top:10px">
        ${d.stores.map(s => `
          <div class="store-row">
            <div class="t">${escapeHtml(s.name)}</div>
            ${s.address ? `<div class="a">${escapeHtml(s.address)}</div>` : ""}
          </div>`).join("")}
      </div>`;
  } catch (e) {
    box.innerHTML = nowFallback("门店信息加载失败，请确认服务运行中。");
  }
}

/* ---------------- 倒计时 ---------------- */
function tickCountdown() {
  const diff = new Date(DEADLINE).getTime() - Date.now();
  const t = Math.max(0, diff);
  const d = Math.floor(t / 86400000);
  const h = Math.floor(t % 86400000 / 3600000);
  const m = Math.floor(t % 3600000 / 60000);
  const cd = $("#countdown");
  if (cd) {
    cd.querySelector('[data-cd=d]').textContent = String(d).padStart(2, "0");
    cd.querySelector('[data-cd=h]').textContent = String(h).padStart(2, "0");
    cd.querySelector('[data-cd=m]').textContent = String(m).padStart(2, "0");
  }
  const st = $("#stCd");
  if (st) st.textContent = `${d}天${String(h).padStart(2, "0")}时`;
}
tickCountdown();
setInterval(tickCountdown, 30000);

/* ---------------- 初始化 ---------------- */
async function loadProvinces() {
  try {
    PROVINCES = await (await fetch("/api/provinces")).json();
  } catch (e) {
    PROVINCES = [];
  }
  const sel = $("#provinceFilter");
  PROVINCES.forEach(p => sel.add(new Option(p, p)));
}

(async function init() {
  await loadVoteCapabilities();                 // 先拿能力，再渲染，避免按钮先亮后灰
  await Promise.allSettled([loadAccount(), loadProvinces(), loadProducts()]);
  renderHall();                                 // 按最终能力重绘按钮状态
  if (!VOTE_CAPS.voting_available) {
    console.info("[McMuseum] 在线投票不可用：", VOTE_CAPS.code || VOTE_CAPS.mode);
  }
})();

/* ---------------- 回到顶部 ---------------- */
const toTopBtn = $("#toTop");
window.addEventListener("scroll", () => {
  toTopBtn.classList.toggle("show", window.scrollY > 400);
}, { passive: true });
toTopBtn.addEventListener("click", () => window.scrollTo({ top: 0, behavior: "smooth" }));
