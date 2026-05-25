/** Full page reload — clears in-memory SPA state (same practical effect as manual hard refresh). */
export function hardReloadPage(): void {
  const url = new URL(window.location.href);
  url.searchParams.set("_hbm", String(Date.now()));
  window.location.replace(url.toString());
}
