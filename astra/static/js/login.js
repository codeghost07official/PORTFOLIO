/* PIN entry: one box per digit, auto-advance, backspace-back, paste, Enter/auto submit. */
(() => {
  const form = document.getElementById("pin-form");
  if (!form) return;
  const boxes = [...form.querySelectorAll(".pin-digit")];
  const hidden = document.getElementById("pin-value");
  let sent = false;

  const value = () => boxes.map((b) => b.value).join("");
  const submit = () => {
    if (sent || value().length !== 4) return;
    sent = true;
    hidden.value = value();
    boxes.forEach((b) => (b.readOnly = true));
    form.submit();
  };
  const fill = (digits, from = 0) => {
    digits.split("").forEach((d, i) => { if (boxes[from + i]) boxes[from + i].value = d; });
    const next = boxes.find((b) => !b.value);
    (next || boxes[boxes.length - 1]).focus();
    if (!next) submit();
  };

  boxes.forEach((box, i) => {
    box.addEventListener("input", () => {
      const digits = box.value.replace(/\D/g, "");
      box.value = "";
      if (digits) fill(digits, i);
    });
    box.addEventListener("keydown", (e) => {
      if (e.key === "Backspace" && !box.value && i > 0) { boxes[i - 1].value = ""; boxes[i - 1].focus(); e.preventDefault(); }
      else if (e.key === "ArrowLeft" && i > 0) boxes[i - 1].focus();
      else if (e.key === "ArrowRight" && i < 3) boxes[i + 1].focus();
      else if (e.key === "Enter") { e.preventDefault(); submit(); }
    });
    box.addEventListener("paste", (e) => {
      e.preventDefault();
      const digits = (e.clipboardData?.getData("text") || "").replace(/\D/g, "").slice(0, 4);
      if (digits) { boxes.forEach((b) => (b.value = "")); fill(digits, 0); }
    });
    box.addEventListener("focus", () => box.select());
  });
  form.addEventListener("submit", (e) => { e.preventDefault(); submit(); });
  if (form.querySelector(".login-err")) boxes[0].focus();
})();
