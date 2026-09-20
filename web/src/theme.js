import { computed, ref } from "vue";

const STORAGE_KEY = "bambu-timelapse-theme";
const media = window.matchMedia("(prefers-color-scheme: dark)");
const preference = ref(localStorage.getItem(STORAGE_KEY) || "system");
const systemTheme = ref(media.matches ? "dark" : "light");

function resolvedTheme() {
  return preference.value === "system"
    ? systemTheme.value
    : preference.value;
}

function applyTheme() {
  document.documentElement.dataset.theme = resolvedTheme();
  document.documentElement.style.colorScheme = resolvedTheme();
}

function onSystemThemeChange(event) {
  systemTheme.value = event.matches ? "dark" : "light";

  if (preference.value === "system") {
    applyTheme();
  }
}

media.addEventListener?.("change", onSystemThemeChange);
applyTheme();

export const themeState = {
  preference,
  systemTheme,
  resolved: computed(resolvedTheme)
};

export function toggleTheme() {
  const next = resolvedTheme() === "dark" ? "light" : "dark";
  preference.value = next;
  localStorage.setItem(STORAGE_KEY, next);
  applyTheme();
}

export function useSystemTheme() {
  preference.value = "system";
  localStorage.removeItem(STORAGE_KEY);
  applyTheme();
}
