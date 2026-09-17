const grid = document.querySelector("[data-theme-grid]");
const cards = [...document.querySelectorAll("[data-theme]")];
const search = document.querySelector("[data-search]");
const sort = document.querySelector("[data-sort]");
const count = document.querySelector("[data-visible-count]");
const empty = document.querySelector("[data-empty]");

function updateCatalog() {
  const query = search.value.trim().toLowerCase();
  let visible = 0;

  for (const card of cards) {
    const matches = `${card.dataset.name} ${card.dataset.repository}`.includes(query);
    card.hidden = !matches;
    visible += Number(matches);
  }

  const comparators = {
    popular: (a, b) => Number(b.dataset.downloads) - Number(a.dataset.downloads),
    recent: (a, b) => Number(b.dataset.released) - Number(a.dataset.released),
    name: (a, b) => a.dataset.name.localeCompare(b.dataset.name),
  };
  cards.sort(comparators[sort.value]).forEach((card) => grid.append(card));
  count.textContent = visible;
  empty.hidden = visible !== 0;
}

search.addEventListener("input", updateCatalog);
sort.addEventListener("change", updateCatalog);
updateCatalog();
