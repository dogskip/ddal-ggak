exports.label = function (value) {
  if (value === '') return '(empty)';
  return value.trim();
};
