(() => {
  const standalone = window.matchMedia && window.matchMedia("(display-mode: standalone)").matches;
  let deferredPrompt = null;
  const installButton = document.getElementById("installAppButton");

  if ("serviceWorker" in navigator) {
    window.addEventListener("load", () => {
      navigator.serviceWorker.register("/sw.js", { scope: "/" }).catch(() => {});
    });
  }

  window.addEventListener("beforeinstallprompt", (event) => {
    event.preventDefault();
    deferredPrompt = event;
    if (installButton) installButton.hidden = false;
  });

  window.addEventListener("appinstalled", () => {
    deferredPrompt = null;
    if (installButton) installButton.hidden = true;
  });

  if (installButton) {
    if (standalone) installButton.hidden = true;
    installButton.addEventListener("click", async () => {
      if (!deferredPrompt) return;
      deferredPrompt.prompt();
      await deferredPrompt.userChoice.catch(() => {});
      deferredPrompt = null;
      installButton.hidden = true;
    });
  }
})();
