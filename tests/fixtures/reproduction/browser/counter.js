function increment(value) { return value + 2; }
function reset() { return 0; }

if (typeof module !== 'undefined') module.exports = { increment, reset };
