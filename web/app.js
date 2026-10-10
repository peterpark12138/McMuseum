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
  if (v === "rank") loadRank();
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
