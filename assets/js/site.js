const grid = document.querySelector("[data-theme-grid]");
const cards = [...document.querySelectorAll("[data-theme]")];
const search = document.querySelector("[data-search]");
const sort = document.querySelector("[data-sort]");
const count = document.querySelector("[data-visible-count]");
const empty = document.querySelector("[data-empty]");
const status = document.querySelector("[data-catalog-status]");

const themeCount = (n) => `${n} ${n === 1 ? "theme" : "themes"}`;

// One status message per search or sort, rather than a live region on the grid,
// which would announce every moved card.
let lastMessage = "";
let announceTimer;
function announce(message, delay = 0) {
  clearTimeout(announceTimer);
  announceTimer = setTimeout(() => {
    // VoiceOver skips a message identical to the previous one, so make repeats differ.
    if (message === lastMessage) message += " ";
    lastMessage = message;
    status.textContent = message;
  }, delay);
}

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
  return visible;
}

search.addEventListener("input", () => {
  const visible = updateCatalog();
  const message = search.value.trim()
    ? `${themeCount(visible)} ${visible === 1 ? "matches" : "match"}`
    : `Showing all ${themeCount(visible)}`;
  // Wait for a pause in typing so each keystroke doesn't queue an announcement.
  announce(message, 600);
});
sort.addEventListener("change", () => {
  const visible = updateCatalog();
  announce(`Sorted by ${sort.selectedOptions[0].text.toLowerCase()}, ${themeCount(visible)}`);
});
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

// Safari doesn't support closedby="any", so close on a click outside the dialog
// there. Test the pointer position: the dialog is also the event target for its
// own padding. Requiring the press and release outside keeps a text-selection
// drag that ends on the backdrop from closing it.
if (!("closedBy" in HTMLDialogElement.prototype)) {
  const outside = (event) => {
    const rect = createDialog.getBoundingClientRect();
    return (
      event.clientX < rect.left ||
      event.clientX > rect.right ||
      event.clientY < rect.top ||
      event.clientY > rect.bottom
    );
  };
  let pressedOutside = false;
  createDialog.addEventListener("pointerdown", (event) => {
    pressedOutside = outside(event);
  });
  createDialog.addEventListener("pointerup", (event) => {
    if (pressedOutside && outside(event)) createDialog.close();
    pressedOutside = false;
  });
}

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
