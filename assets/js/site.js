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
    stars: (a, b) =>
      Number(b.dataset.stars) - Number(a.dataset.stars) ||
      comparators.popular(a, b) ||
      comparators.name(a, b),
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

const createLink = document.querySelector("[data-open-create]");
const createDialog = document.querySelector("[data-create-dialog]");
const copyPrompt = document.querySelector("[data-copy-prompt]");

createLink.addEventListener("click", (event) => {
  if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) {
    return;
  }
  event.preventDefault();
  createDialog.showModal();
});

copyPrompt.addEventListener("click", async () => {
  const prompt = document.querySelector("[data-create-prompt]").textContent.trim();
  try {
    await navigator.clipboard.writeText(prompt);
    copyPrompt.textContent = "Copied!";
  } catch {
    copyPrompt.textContent = "Select and copy the prompt above";
  }
});

createDialog.addEventListener("close", () => {
  copyPrompt.textContent = "Copy prompt";
});
