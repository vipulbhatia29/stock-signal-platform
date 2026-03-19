// eslint-disable-next-line @typescript-eslint/no-require-imports
const React = require("react");
function ReactMarkdown({ children }) {
  return React.createElement("div", { "data-testid": "markdown" }, children);
}
module.exports = ReactMarkdown;
module.exports.default = ReactMarkdown;
