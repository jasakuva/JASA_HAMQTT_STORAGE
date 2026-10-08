(() => {
  const updateClock = () => {
    const value = new Intl.DateTimeFormat([], { dateStyle: 'medium', timeStyle: 'short' }).format(new Date());
    document.querySelectorAll('#topbar-clock, #sidebar-clock').forEach((element) => { element.textContent = value; });
  };
  updateClock();
  window.setInterval(updateClock, 30000);
})();