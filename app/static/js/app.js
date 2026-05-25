// Apply colorblind class from localStorage before render (avoids flash)
(function () {
  if (localStorage.getItem('colorblind') === '1') {
    document.body.classList.add('colorblind');
  }
})();

// Wordle share text client-side parser for live preview
function previewScore(text) {
  const re = /^Wordle\s+(?:#TODAY|#?([\d,]+))\s+(X|\d)\/6(\*)?/m;
  const m = text.match(re);
  if (!m) return { valid: false };
  return {
    valid: !!m[3],
    puzzleNumber: m[1] ? parseInt(m[1].replace(/,/g, ''), 10) : null,
    guesses: m[2] === 'X' ? 0 : parseInt(m[2], 10),
    hardMode: !!m[3],
  };
}

// Register service worker
if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/static/js/sw.js').catch(() => {});
  });
}
