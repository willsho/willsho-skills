const data = [
  { n: "+38%", l: "MAU 环比" },
  { n: "¥1.2M", l: "新增 ARR" },
  { n: "62%", l: "次月留存" },
];
const root = document.getElementById("metrics");
for (const d of data) {
  const el = document.createElement("div");
  el.className = "tile";
  el.innerHTML = `<div class="n">${d.n}</div><div class="l">${d.l}</div>`;
  root.appendChild(el);
}
