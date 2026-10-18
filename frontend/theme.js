// Runs before styles on both pages: no light flash and no network/storage of personal data.
(() => {
  const media = window.matchMedia("(prefers-color-scheme: dark)");
  let mode = "system";
  try { mode = JSON.parse(localStorage.getItem("seruen_theme")) || "system"; } catch { /* private mode */ }
  if (!["system", "light", "dark"].includes(mode)) mode = "system";
  function apply() {
    const dark = mode === "dark" || (mode === "system" && media.matches);
    document.documentElement.dataset.theme = dark ? "dark" : "light";
    document.documentElement.style.colorScheme = dark ? "dark" : "light";
    const meta = document.querySelector('meta[name="theme-color"]');
    if (meta) meta.content = dark ? "#112936" : "#00708A";
  }
  window.SeruenTheme = {
    get mode() { return mode; },
    cycle() {
      mode = {system: "dark", dark: "light", light: "system"}[mode];
      try { localStorage.setItem("seruen_theme", JSON.stringify(mode)); } catch { /* private mode */ }
      apply();
    },
  };
  media.addEventListener?.("change", apply);
  apply();
})();
