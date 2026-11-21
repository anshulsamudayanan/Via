export type Theme = "dark" | "light";

export const THEME_STORAGE_KEY = "via-theme";

/**
 * Runs before first paint (inlined in <head>) so the page never flashes the
 * wrong theme. Dark is the default; a saved preference wins.
 */
export const themeInitScript = `(function(){try{var t=localStorage.getItem("${THEME_STORAGE_KEY}");document.documentElement.dataset.theme=t==="light"?"light":"dark";}catch(e){document.documentElement.dataset.theme="dark";}})();`;
