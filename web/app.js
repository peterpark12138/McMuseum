// 麦麦复活赛 前端逻辑：投票大厅 / 复活榜 / 投票交互
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];

const ICONS = ["🍔","🍟","🥤","🍦","🍗","🌭","🥟","🥞","🍩","🍱","🧇","🍪"];

let PRODUCTS = [];
let PROVINCES = [];
let AUTO_PROVINCE = "";

function iconFor(p, i) {
  if (/甜品|麦旋风|派|奶昔|圣代|冰淇淋|雪/.test(p.category || "")) return "🍦";
  if (/饮|可乐|酷|茶|朱古力/.test(p.name + (p.category||""))) return "🥤";
  if (/鸡|翅|鸡排|鸡腿|炸/.test(p.name + (p.category||""))) return "🍗";
  if (/薯|薯角|薯条/.test(p.name)) return "🍟";
  if (/卷|饼|肉夹馍|馍|三角/.test(p.name)) return "🥟";
  return ICONS[i % ICONS.length];
}

// ---- 视图切换 ----
$$(".tab").forEach(t => t.addEventListener("click", () => {
  $$(".tab").forEach(x => x.classList.remove("active"));
  t.classList.add("active");
  const v = t.dataset.view;
  $("#view-hall").classList.toggle("hidden", v !== "hall");
  $("#view-rank").classList.toggle("hidden", v !== "rank");
  $("#view-now").classList.toggle("hidden", v !== "now");
  if (v === "rank") loadRank();
  if (v === "now") loadNow();
}));

// ---- 加载省份枚举（受控，防脏数据）----
async function loadProvinces() {
  try {
    PROVINCES = await (await fetch("/api/provinces")).json();
  } catch (e) {
    PROVINCES = [];
  }
  const sel = $("#province-filter");
  if (sel) {
    PROVINCES.forEach(p => sel.add(new Option(p, p)));
  }
}

// ---- 自动识别省份（仅省级，不取地址）----
async function detectProvince() {
  try {
    const d = await (await fetch("/api/detect-province")).json();
    AUTO_PROVINCE = d.province || "";
  } catch (e) {
    AUTO_PROVINCE = "";
  }
}

// ---- 加载单品 ----
async function loadProducts() {
  try {
    const res = await fetch("/api/products");
    PRODUCTS = await res.json();
    renderGrid();
  } catch (e) {
    $("#hall-empty").classList.remove("hidden");
  }
}

function renderGrid() {
  const grid = $("#grid");
  grid.innerHTML = "";
  if (!PRODUCTS.length) { $("#hall-empty").classList.remove("hidden"); return; }
  $("#hall-empty").classList.add("hidden");
  PRODUCTS.forEach((p, i) => {
    const card = document.createElement("div");
    card.className = "card";
    card.innerHTML = `
      <div class="card-ribbon">怀旧</div>
      <div class="card-band">${iconFor(p, i)}</div>
      <div class="card-body">
        <div class="card-name">${p.name}</div>
        <span class="card-era">${p.era || "限定"}</span>
        <div class="card-story">${p.story || ""}</div>
        <div class="card-foot">
          <span class="votes-pill"><b>${p.votes}</b> 票</span>
          <button class="vote-btn" data-id="${p.id}">投一票</button>
        </div>
      </div>`;
    card.querySelector(".vote-btn").addEventListener("click", () => openVote(p));
    grid.appendChild(card);
  });
}

// ---- 复活榜 ----
async function loadRank() {
  const list = $("#rank-list");
  list.innerHTML = "<div class='state'>加载中…</div>";
  try {
    const sel = $("#province-filter");
    const province = sel ? sel.value : "";
    const url = province ? `/api/leaderboard?province=${encodeURIComponent(province)}` : "/api/leaderboard";
    const res = await fetch(url);
    const data = await res.json();
    const items = data.items || [];
    if (!items.length) {
      list.innerHTML = "";
      $("#rank-empty").classList.remove("hidden");
      return;
    }
    $("#rank-empty").classList.add("hidden");
    const max = items[0].votes || 1;
    const notice = (data.fallback && province)
      ? `<div class="state notice">${escapeHtml(province)} 还没有人投票，先看看全国榜 👇</div>`
      : "";
    list.innerHTML = notice + items.map((it, i) => `
      <div class="rank-row ${i < 3 ? "top" + (i + 1) : ""}">
        <div class="rank-no">${i === 0 ? "🥇" : i === 1 ? "🥈" : i === 2 ? "🥉" : i + 1}</div>
        <div class="rank-main">
          <div class="rank-name">${it.name}</div>
          <div class="rank-bar"><i style="width:${(it.votes / max * 100).toFixed(1)}%"></i></div>
        </div>
        <div class="rank-votes">${it.votes} 票</div>
      </div>`).join("");
  } catch (e) {
    list.innerHTML = "";
    $("#rank-empty").textContent = "榜单加载失败，请确认服务运行中。";
    $("#rank-empty").classList.remove("hidden");
  }
}
$("#refresh-rank").addEventListener("click", loadRank);
$("#province-filter").addEventListener("change", loadRank);

// 营养库搜索
function bindNutrition() {
  const input = $("#nut-input");
  const btn = $("#nut-btn");
  if (!input || !btn) return;
  const go = () => loadNutrition(input.value.trim());
  btn.addEventListener("click", go);
  input.addEventListener("keydown", e => { if (e.key === "Enter") go(); });
}
bindNutrition();

// ---- 投票弹窗 ----
let current = null;
function openVote(p) {
  current = p;
  const opts = PROVINCES.map(x =>
    `<option value="${x}"${x === AUTO_PROVINCE ? " selected" : ""}>${x}</option>`).join("");
  const hint = AUTO_PROVINCE
    ? `<p class="auto-hint">📍 已自动识别为 <b>${escapeHtml(AUTO_PROVINCE)}</b>，可修改（仅统计到省级，不保存地址）</p>`
    : `<p class="auto-hint dim">未自动识别到省份，默认计入全国；也可手动选择</p>`;
  $("#modal-body").innerHTML = `
    <h3>给《${p.name}》打 call？</h3>
    <p>将以你的 <b>麦当劳会员身份</b> 投票：<br/>1 票基础身份票 + 每 100 积分再加 1 票。</p>
    <div class="modal-field">
      <label for="vote-province">省份（自动识别 · 可修改）</label>
      <select id="vote-province" class="province-select">
        <option value="">全国（不分省）</option>
        ${opts}
      </select>
      ${hint}
    </div>
    <button class="confirm-btn" id="do-vote">确认投票</button>
    <button class="cancel-btn" id="cancel-vote">再想想</button>`;
  $("#modal").classList.remove("hidden");
  $("#do-vote").addEventListener("click", doVote);
  $("#cancel-vote").addEventListener("click", closeModal);
}
function closeModal() { $("#modal").classList.add("hidden"); current = null; }
$("#modal-close").addEventListener("click", closeModal);
$("#modal").addEventListener("click", e => { if (e.target.id === "modal") closeModal(); });

async function doVote() {
  if (!current) return;
  const btn = $("#do-vote");
  btn.disabled = true; btn.textContent = "投票中…";
  const provinceEl = $("#vote-province");
  const province = provinceEl ? provinceEl.value : "";
  try {
    const res = await fetch("/api/vote", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ product: current.id, province })
    });
    const data = await res.json();
    if (data.ok) {
      $("#modal-body").innerHTML = `
        <div class="ok-emoji">🎉</div>
        <h3>投票成功！</h3>
        <div class="big">+${data.val} 票</div>
        <p>${escapeHtml(data.msg)}</p>
        <button class="confirm-btn" id="done">好耶</button>`;
      $("#done").addEventListener("click", closeModal);
      toast("投票成功，感谢支持老麦 🍟", "ok");
      // 同步更新本地数据
      const p = PRODUCTS.find(x => x.id === current.id);
      if (p) p.votes += data.val;
      renderGrid();
      if (!$("#view-rank").classList.contains("hidden")) loadRank();
    } else {
      $("#modal-body").innerHTML = `
        <div class="ok-emoji">😅</div>
        <h3>投票没成功</h3>
        <p>${escapeHtml(data.msg)}</p>
        <button class="confirm-btn" id="done">知道了</button>`;
      $("#done").addEventListener("click", closeModal);
      toast("投票未成功，看提示～", "err");
    }
  } catch (e) {
    $("#modal-body").innerHTML = `<h3>网络错误</h3><p>无法连接服务，请确认 serve.py 在运行。</p>
      <button class="confirm-btn" id="done">关闭</button>`;
    $("#done").addEventListener("click", closeModal);
  } finally {
    btn.disabled = false; btn.textContent = "确认投票";
  }
}

// ---- 麦麦现在（麦当劳实时只读增强）----
async function loadNow() {
  await Promise.allSettled([loadOnSale(), loadCampaigns(), loadMall(), loadLottery(), loadNutrition(), loadNearby()]);
}

async function loadOnSale() {
  const box = $("#onsale-list");
  box.innerHTML = "<div class='state'>加载中…</div>";
  try {
    const d = await (await fetch("/api/on-sale")).json();
    if (d.fallback) {
      box.innerHTML = nowFallback("🍔 在售对比需要连接你的麦当劳账号（配置 MCD_MCP_TOKEN）后实时比对。");
      return;
    }
    const cmp = d.comparison || {};
    const rows = (PRODUCTS.length ? PRODUCTS : await (await fetch("/api/products")).json())
      .map(p => ({ p, c: cmp[p.id] || { available: false, matched: null } }));
    if (!rows.length) { box.innerHTML = ""; return; }
    box.innerHTML = rows.map(({ p, c }) => {
      const tag = c.available
        ? `<span class="os-tag on">仍在售 · ${escapeHtml(c.matched || "")}</span>`
        : `<span class="os-tag off">已绝版</span>`;
      return `<div class="os-row">
        <div class="os-name">${escapeHtml(p.name)} <span class="os-era">${escapeHtml(p.era || "")}</span></div>
        ${tag}
      </div>`;
    }).join("") + `<p class="os-foot">当前在售餐品共 <b>${(d.meals || []).length}</b> 款 · 数据来自 query-meals 实时接口</p>`;
  } catch (e) {
    box.innerHTML = nowFallback("在售对比加载失败，请确认服务运行中。");
  }
}

async function loadCampaigns() {
  const box = $("#campaigns-list");
  box.innerHTML = "<div class='state'>加载中…</div>";
  try {
    const d = await (await fetch("/api/campaigns")).json();
    if (d.fallback || !d.items || !d.items.length) {
      box.innerHTML = nowFallback("📣 营销活动日历需要连接麦当劳账号后实时展示。");
      return;
    }
    box.innerHTML = d.items.map(it => `
      <div class="camp-card">
        ${it.image ? `<img src="${it.image}" alt="" loading="lazy"/>` : ""}
        <div class="camp-body">
          <div class="camp-title">${escapeHtml(it.title)}</div>
          ${it.date ? `<div class="camp-date">${escapeHtml(it.date)}</div>` : ""}
        </div>
      </div>`).join("");
  } catch (e) {
    box.innerHTML = nowFallback("活动加载失败，请确认服务运行中。");
  }
}

async function loadMall() {
  const box = $("#mall-list");
  box.innerHTML = "<div class='state'>加载中…</div>";
  try {
    const d = await (await fetch("/api/points-mall")).json();
    if (d.fallback || !d.items || !d.items.length) {
      box.innerHTML = nowFallback("🎁 积分商城需要连接麦当劳账号后实时展示。");
      return;
    }
    box.innerHTML = d.items.map(it => `
      <div class="mall-card">
        <div class="mall-name">${escapeHtml(it.spuName)}</div>
        <div class="mall-point">${escapeHtml(String(it.point))} 积分</div>
        ${it.selling ? `<div class="mall-sell">${escapeHtml(it.selling)}</div>` : ""}
      </div>`).join("");
  } catch (e) {
    box.innerHTML = nowFallback("积分商城加载失败，请确认服务运行中。");
  }
}

async function loadLottery() {
  const box = $("#lottery-box");
  box.innerHTML = "<div class='state'>加载中…</div>";
  try {
    const d = await (await fetch("/api/lottery")).json();
    if (d.fallback || !d.info || !Object.keys(d.info).length) {
      box.innerHTML = nowFallback("🎰 抽奖信息需要连接麦当劳账号后实时展示。");
      return;
    }
    const info = d.info;
    const prizes = (info.prizes || []).filter(Boolean);
    box.innerHTML = `
      <div class="lottery-card">
        <div class="lottery-status">${escapeHtml(info.activityStatusText || info.statusText || "活动中")}</div>
        ${info.cost ? `<div class="lottery-cost">单次消耗：${escapeHtml(String(info.cost))}</div>` : ""}
        ${prizes.length ? `<div class="lottery-prizes"><b>奖品含：</b>${prizes.map(escapeHtml).join("、")}</div>` : ""}
        <p class="lottery-note">本作品仅读取活动信息，绝不代你抽奖 / 扣积分。</p>
      </div>`;
  } catch (e) {
    box.innerHTML = nowFallback("抽奖信息加载失败，请确认服务运行中。");
  }
}

async function loadNutrition(name) {
  const box = $("#nut-list");
  box.innerHTML = "<div class='state'>加载中…</div>";
  try {
    const url = name ? `/api/nutrition?name=${encodeURIComponent(name)}` : "/api/nutrition";
    const d = await (await fetch(url)).json();
    if (d.fallback || !d.items || !d.items.length) {
      box.innerHTML = nowFallback(name ? "未找到匹配营养数据。" : "🥗 营养库需要连接麦当劳账号后实时展示。");
      return;
    }
    box.innerHTML = d.items.slice(0, 40).map(it => `
      <div class="nut-row">
        <div class="nut-name">${escapeHtml(it.productName)}</div>
        <div class="nut-metrics">
          <span>🔥 ${escapeHtml(it.energyKcal)} kcal</span>
          <span>💪 蛋白 ${escapeHtml(it.protein)}g</span>
          <span>🧈 脂肪 ${escapeHtml(it.fat)}g</span>
          <span>🍞 碳水 ${escapeHtml(it.carbohydrate)}g</span>
        </div>
      </div>`).join("") + (d.items.length > 40 ? `<p class="os-foot">仅显示前 40 条，可缩小关键词。</p>` : "");
  } catch (e) {
    box.innerHTML = nowFallback("营养库加载失败，请确认服务运行中。");
  }
}

async function loadNearby() {
  const box = $("#nearby-box");
  box.innerHTML = "<div class='state'>加载中…</div>";
  try {
    const d = await (await fetch("/api/nearby")).json();
    if (d.fallback) {
      box.innerHTML = nowFallback("📍 附近门店需要连接麦当劳账号（用于只读配送地址省份）后展示。");
      return;
    }
    const stores = d.stores || [];
    const head = d.province ? `<p class="nearby-prov">已识别省份：<b>${escapeHtml(d.province)}</b>（仅省级，未保存地址）</p>` : "";
    if (!stores.length) {
      box.innerHTML = head + nowFallback("该地址暂无可配送门店数据。");
      return;
    }
    box.innerHTML = head + stores.map(s => `
      <div class="nearby-row">
        <div class="nearby-name">🏠 ${escapeHtml(s.name)}</div>
        ${s.address ? `<div class="nearby-addr">${escapeHtml(s.address)}</div>` : ""}
      </div>`).join("");
  } catch (e) {
    box.innerHTML = nowFallback("附近门店加载失败，请确认服务运行中。");
  }
}

function nowFallback(msg) {
  return `<div class="now-fallback">${escapeHtml(msg)}</div>`;
}

function escapeHtml(s) {
  return String(s || "").replace(/[&<>]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));
}

let toastTimer;
function toast(msg, kind) {
  const t = $("#toast");
  t.textContent = msg;
  t.className = "toast " + (kind || "");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.classList.add("hidden"), 2600);
}

loadProvinces().then(detectProvince);
loadProducts();
