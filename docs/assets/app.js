const PAGE = 24;
const STATUS_LABEL = {
  upcoming: "即将上拍",
  preview: "预展",
  sold: "已成交",
  unsold: "未成交",
  withdrawn: "撤拍",
  closed: "已结束，成交价未公开",
};
const CITY = {
  "Hong Kong": "香港",
  London: "伦敦",
  "New York": "纽约",
  Paris: "巴黎",
  Shanghai: "上海",
  Geneva: "日内瓦",
  Beijing: "北京",
};

const state = {
  data: null,
  sale: "",
  page: 1,
};

const $ = (id) => document.getElementById(id);

function place(name) {
  return CITY[name] || name || "";
}

function money(amount, currency) {
  if (!amount) return "";
  const raw = String(amount).replace(/,/g, "");
  const num = Number(raw);
  const shown = Number.isFinite(num) ? num.toLocaleString("zh-CN") : String(amount);
  return currency ? `${currency} ${shown}` : shown;
}

function estimateText(lot) {
  if (lot.estimate && /[A-Za-z\u4e00-\u9fff]/.test(lot.estimate) && !/^\d/.test(lot.estimate)) {
    return lot.estimate;
  }
  if (lot.estimate && lot.estimate.includes("-") && lot.currency) {
    const [low, high] = lot.estimate.split("-");
    if (low && high) return `${lot.currency} ${Number(low).toLocaleString("zh-CN")}–${Number(high).toLocaleString("zh-CN")}`;
  }
  return lot.estimate || "";
}

function dateLabel(lot) {
  if (lot.sale_date_label && lot.sale_date_label !== lot.sale_date) return lot.sale_date_label;
  return lot.sale_date || "";
}

function isNew(lot) {
  const today = state.data.today || (state.data.generated_at || "").slice(0, 10);
  return (lot.first_seen_at || "").slice(0, 10) === today;
}

function matches(lot) {
  const q = $("q").value.trim().toLowerCase();
  const house = $("house").value;
  const status = $("status").value;
  const category = $("category").value;
  const onlyNew = $("only-new").checked;
  if (house && lot.house_id !== house) return false;
  if (status && lot.status !== status) return false;
  if (category === "__none__" && lot.category) return false;
  if (category && category !== "__none__" && lot.category !== category) return false;
  if (onlyNew && !isNew(lot)) return false;
  if (state.sale && `${lot.house_id}|${lot.sale_code}` !== state.sale) return false;
  if (!q) return true;
  const hay = [lot.title, lot.sale_title, lot.lot_number, lot.house, lot.period, lot.category]
    .join(" ")
    .toLowerCase();
  return hay.includes(q);
}

function sortLots(list) {
  const mode = $("sort").value;
  const copy = list.slice();
  const lotKey = (value) => {
    const n = String(value || "").match(/\d+/);
    return n ? Number(n[0]) : 1e12;
  };
  const upcoming = (lot) => (lot.status === "upcoming" || lot.status === "preview" ? 0 : 1);
  copy.sort((a, b) => {
    if (mode === "new") {
      const day = (lot) => (lot.first_seen_at || "").slice(0, 10);
      const seen = day(b).localeCompare(day(a));
      if (seen) return seen;
    }
    if (mode === "recent") {
      const date = (b.sale_end || b.sale_date || "").localeCompare(a.sale_end || a.sale_date || "");
      if (date) return date;
    } else {
      const rank = upcoming(a) - upcoming(b);
      if (rank) return rank;
      const dir = upcoming(a) === 0 ? 1 : -1;
      const date = (a.sale_date || "").localeCompare(b.sale_date || "");
      if (date) return date * dir;
    }
    const sale = (a.sale_title || "").localeCompare(b.sale_title || "", "zh");
    if (sale) return sale;
    return lotKey(a.lot_number) - lotKey(b.lot_number);
  });
  return copy;
}

function renderHouses() {
  const root = $("houses");
  root.replaceChildren();
  for (const house of state.data.houses || []) {
    const card = document.createElement("article");
    card.className = "house-card " + (house.ok && house.lots ? "ok" : "down");
    const title = document.createElement("h3");
    title.textContent = house.name;
    const count = document.createElement("div");
    count.className = "count";
    count.textContent = house.lots ? `${house.lots} 件 · ${house.sales} 场` : "本轮无条目";
    const note = document.createElement("p");
    note.textContent = house.note || "";
    card.append(title, count, note);
    root.append(card);
  }
}

function fillFilters() {
  const house = $("house");
  const seen = new Set();
  for (const lot of state.data.lots) {
    if (seen.has(lot.house_id)) continue;
    seen.add(lot.house_id);
    const option = document.createElement("option");
    option.value = lot.house_id;
    option.textContent = lot.house;
    house.append(option);
  }
  const category = $("category");
  const names = [...new Set(state.data.lots.map((lot) => lot.category).filter(Boolean))].sort((a, b) =>
    a.localeCompare(b, "zh")
  );
  for (const name of names) {
    const option = document.createElement("option");
    option.value = name;
    option.textContent = name;
    category.append(option);
  }
  if (state.data.lots.some((lot) => !lot.category)) {
    const option = document.createElement("option");
    option.value = "__none__";
    option.textContent = "官网未标品类";
    category.append(option);
  }
}

function renderSales() {
  const root = $("sales");
  root.replaceChildren();
  const sales = (state.data.sales || []).filter((sale) => {
    const house = $("house").value;
    return !house || sale.house_id === house;
  });
  $("sale-count").textContent = sales.length ? `${sales.length} 场` : "";
  const all = document.createElement("button");
  all.type = "button";
  all.className = "sale-chip" + (state.sale ? "" : " active");
  all.innerHTML = "";
  const who = document.createElement("div");
  who.className = "who";
  who.textContent = "全部专场";
  const name = document.createElement("div");
  name.className = "name";
  name.textContent = "不限专场";
  const when = document.createElement("div");
  when.className = "when";
  when.textContent = `${state.data.lot_count || 0} 件`;
  all.append(who, name, when);
  all.addEventListener("click", () => {
    state.sale = "";
    state.page = 1;
    render();
  });
  root.append(all);
  for (const sale of sales) {
    const button = document.createElement("button");
    button.type = "button";
    const key = `${sale.house_id}|${sale.sale_code}`;
    button.className = "sale-chip" + (state.sale === key ? " active" : "");
    const house = document.createElement("div");
    house.className = "who";
    house.textContent = sale.house;
    const title = document.createElement("div");
    title.className = "name";
    title.textContent = sale.sale_title;
    const whenLine = document.createElement("div");
    whenLine.className = "when";
    const bits = [sale.sale_date_label || sale.sale_date, place(sale.sale_location), `${sale.lots} 件`];
    if (sale.upcoming) bits.push("有未开拍");
    whenLine.textContent = bits.filter(Boolean).join(" · ");
    button.append(house, title, whenLine);
    button.addEventListener("click", () => {
      state.sale = key;
      state.page = 1;
      render();
    });
    root.append(button);
  }
}

function renderCards(list) {
  const cards = $("cards");
  const empty = $("state");
  cards.replaceChildren();
  if (!list.length) {
    empty.classList.remove("hidden");
    empty.textContent = "这一组条件下没有拍品。换个拍行、状态，或清掉专场筛选。";
    $("pager").replaceChildren();
    $("lot-count").textContent = "0 件";
    return;
  }
  empty.classList.add("hidden");
  const pages = Math.max(1, Math.ceil(list.length / PAGE));
  if (state.page > pages) state.page = pages;
  const start = (state.page - 1) * PAGE;
  const slice = list.slice(start, start + PAGE);
  $("lot-count").textContent = `显示 ${start + 1}–${start + slice.length} / ${list.length} 件`;
  for (const lot of slice) {
    const card = document.createElement("article");
    card.className = "card";
    const thumb = document.createElement("div");
    thumb.className = "thumb";
    if (lot.image_hotlink && lot.image_urls && lot.image_urls[0]) {
      const img = document.createElement("img");
      img.alt = "官网缩略图，版权归拍行";
      img.src = lot.image_urls[0];
      img.addEventListener("error", () => {
        img.remove();
        thumb.textContent = "官网图片未能显示，请点进原页";
      });
      thumb.append(img);
    } else {
      thumb.textContent = lot.image_urls && lot.image_urls.length ? "图片请至官网查看" : "官网未给出可热链缩略图";
    }
    const body = document.createElement("div");
    const kicker = document.createElement("div");
    kicker.className = "kicker";
    const house = document.createElement("span");
    house.className = "pill";
    house.textContent = lot.house;
    const status = document.createElement("span");
    status.className = "pill" + (lot.status === "sold" ? " sold" : "");
    status.textContent = STATUS_LABEL[lot.status] || lot.status || "状态未标";
    kicker.append(house, status);
    if (isNew(lot)) {
      const fresh = document.createElement("span");
      fresh.className = "pill new";
      fresh.textContent = "新见";
      kicker.append(fresh);
    }
    const heading = document.createElement("h3");
    heading.textContent = lot.lot_number ? `Lot ${lot.lot_number}  ${lot.title}` : lot.title;
    const sub = document.createElement("p");
    sub.className = "sub";
    sub.textContent = [lot.sale_title, dateLabel(lot), place(lot.sale_location)].filter(Boolean).join(" · ");
    const extra = document.createElement("p");
    extra.className = "sub";
    extra.textContent = [lot.period, lot.category].filter(Boolean).join(" · ");
    body.append(kicker, heading, sub);
    if (extra.textContent) body.append(extra);
    const prices = document.createElement("dl");
    prices.className = "prices";
    const addPrice = (label, value) => {
      if (!value) return;
      const dt = document.createElement("dt");
      dt.textContent = label;
      const dd = document.createElement("dd");
      dd.textContent = value;
      prices.append(dt, dd);
    };
    addPrice("估价", estimateText(lot));
    addPrice("落槌", money(lot.hammer_price, lot.currency));
    addPrice("成交价", money(lot.sold_price, lot.currency));
    if (prices.childNodes.length) body.append(prices);
    if (lot.official_url) {
      const link = document.createElement("a");
      link.className = "go";
      link.href = lot.official_url;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      link.textContent = "官网拍品页";
      body.append(link);
    }
    card.append(thumb, body);
    cards.append(card);
  }
  const pager = $("pager");
  pager.replaceChildren();
  if (pages > 1) {
    const prev = document.createElement("button");
    prev.type = "button";
    prev.textContent = "上一页";
    prev.disabled = state.page <= 1;
    prev.addEventListener("click", () => {
      state.page -= 1;
      render();
      $("cards").scrollIntoView({ block: "start" });
    });
    const label = document.createElement("span");
    label.textContent = `${state.page} / ${pages}`;
    const next = document.createElement("button");
    next.type = "button";
    next.textContent = "下一页";
    next.disabled = state.page >= pages;
    next.addEventListener("click", () => {
      state.page += 1;
      render();
      $("cards").scrollIntoView({ block: "start" });
    });
    pager.append(prev, label, next);
  }
}

function render() {
  renderSales();
  const list = sortLots((state.data.lots || []).filter(matches));
  renderCards(list);
}

function showMeta() {
  const when = state.data.generated_at || "";
  const row = $("meta-row");
  row.replaceChildren();
  const generated = document.createElement("span");
  generated.innerHTML = "";
  generated.append("更新于 ");
  const strong = document.createElement("strong");
  strong.textContent = when.replace("T", " ").replace("+08:00", " 上海");
  generated.append(strong);
  const count = document.createElement("span");
  count.textContent = `窗口内 ${state.data.lot_count || 0} 件`;
  const fresh = document.createElement("span");
  fresh.textContent = `今日新见 ${state.data.today_new_count || 0} 件`;
  const windowStart = document.createElement("span");
  windowStart.textContent = `收录 ${state.data.window_start || ""} 之后的已结束专场，以及全部未结束专场`;
  row.append(generated, count, fresh, windowStart);
}

async function main() {
  const stateBox = $("state");
  try {
    const response = await fetch("data/lots.json", { cache: "no-store" });
    if (!response.ok) throw new Error("目录文件还没生成");
    state.data = await response.json();
    if (!state.data.lots) throw new Error("目录格式不对");
    showMeta();
    renderHouses();
    fillFilters();
    render();
  } catch (error) {
    stateBox.classList.add("error");
    stateBox.textContent = `目录没有读出来：${error.message}。先在仓库根目录运行 python3 scripts/update.py。`;
  }
}

for (const id of ["q", "house", "status", "category", "sort", "only-new"]) {
  $(id).addEventListener("input", () => {
    state.page = 1;
    if (state.data) render();
  });
}

main();
