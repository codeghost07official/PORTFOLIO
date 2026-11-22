/* Loaded synchronously in <head>: handle cross-document View Transition promises.
   Chrome rejects them when a transition is skipped (tab hidden, fast double navigation);
   unhandled, that shows up as a console error even though the page loads normally. */
(function () {
  "use strict";
  var quiet = function (vt) {
    if (!vt) return;
    ["ready", "finished", "updateCallbackDone"].forEach(function (k) {
      if (vt[k] && vt[k].catch) vt[k].catch(function () {});
    });
  };
  window.addEventListener("pagereveal", function (e) { quiet(e.viewTransition); });
  window.addEventListener("pageswap", function (e) { quiet(e.viewTransition); });
})();
