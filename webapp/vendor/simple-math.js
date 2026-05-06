window.renderPaperMath = function renderPaperMath(root = document) {
  const escapeText = (value) => String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  const nodes = [];
  while (walker.nextNode()) {
    const node = walker.currentNode;
    if (node.parentElement?.closest("script, style, textarea, input, .no-math")) continue;
    if (/(\$\$?|\\\(|\\\[)/.test(node.nodeValue || "")) nodes.push(node);
  }
  nodes.forEach((node) => {
    const text = escapeText(node.nodeValue || "");
    const html = text
      .replace(/\$\$([^$]+)\$\$/g, '<span class="math-display">$1</span>')
      .replace(/\\\[([\s\S]+?)\\\]/g, '<span class="math-display">$1</span>')
      .replace(/\$([^$\n]+)\$/g, '<span class="math-inline">$1</span>')
      .replace(/\\\(([\s\S]+?)\\\)/g, '<span class="math-inline">$1</span>');
    if (html === text) return;
    const span = document.createElement("span");
    span.innerHTML = html;
    node.parentNode?.replaceChild(span, node);
  });
};
