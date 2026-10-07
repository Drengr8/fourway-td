(() => {
  const cells = document.getElementById("cells");
  if (!cells) return;

  const SIZE = 5;
  const nodes = [];
  for (let i = 0; i < SIZE * SIZE; i += 1) {
    const cell = document.createElement("div");
    cell.className = "cell";
    cells.appendChild(cell);
    nodes.push(cell);
  }

  const pattern = [6, 7, 8, 11, 13, 16, 17, 18];
  let tick = 0;

  const paint = () => {
    nodes.forEach((n) => n.classList.remove("tower"));
    const offset = tick % 3;
    pattern.forEach((idx, i) => {
      if ((i + offset) % 3 !== 0) {
        nodes[idx].classList.add("tower");
      }
    });
    tick += 1;
  };

  paint();
  setInterval(paint, 1600);
})();
