/* Applies the visitor's theme before the page paints (no flash).
   Themes: "signalnova" (default), "light", "dark". Chosen in the nav menu (site.js). */
(function () {
  var t = "signalnova";
  try {
    var saved = localStorage.getItem("sn-theme");
    if (saved === "light" || saved === "dark" || saved === "signalnova") t = saved;
  } catch (e) { /* storage blocked: default theme */ }
  document.documentElement.setAttribute("data-theme", t);
  var bar = { signalnova: "#F5F5FB", light: "#FFFFFF", dark: "#000000" };
  var meta = document.getElementById("themeColor");
  if (meta) meta.setAttribute("content", bar[t]);
})();
