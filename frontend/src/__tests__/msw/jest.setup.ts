/**
 * MSW Jest setup — polyfill fetch globals for jsdom.
 *
 * jsdom does not expose the Node built-in fetch/Response/Request globals.
 * MSW v2 requires these globals in the test environment.
 * Node v18+ provides these built-ins — assign them to global.
 */

// Node v18+ has globalThis.fetch, Response, Request, Headers built-in.
// Assign to global so jsdom test environment can access them.
Object.assign(global, {
  fetch: globalThis.fetch,
  Response: globalThis.Response,
  Request: globalThis.Request,
  Headers: globalThis.Headers,
});

// Ensure TextEncoder / TextDecoder are available (required by msw internals)
if (typeof global.TextEncoder === "undefined") {
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  const { TextEncoder, TextDecoder } = require("util");
  global.TextEncoder = TextEncoder;
  global.TextDecoder = TextDecoder;
}
