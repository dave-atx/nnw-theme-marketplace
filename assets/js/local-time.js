// The UTC text rendered by Hugo stays as the fallback when scripts are off.
const format = new Intl.DateTimeFormat(undefined, {
  year: "numeric",
  month: "long",
  day: "numeric",
  hour: "numeric",
  minute: "2-digit",
  timeZoneName: "short",
});

for (const element of document.querySelectorAll("[data-local-time]")) {
  const date = new Date(element.dateTime);
  if (!Number.isNaN(date.getTime())) element.textContent = format.format(date);
}
