/**
 * Custom jest environment: jsdom + Node fetch globals.
 *
 * MSW v2 requires fetch, Response, Request, Headers to be available as
 * globals in the test environment. jest-environment-jsdom runs in a JSDOM
 * context which does not expose Node's built-in Fetch API.
 *
 * This environment extends jsdom and injects the Node.js Fetch API globals
 * into the jsdom window BEFORE any test modules are loaded.
 */

const JSDOMEnvironment = require("jest-environment-jsdom").default;

class JSDOMEnvironmentWithFetch extends JSDOMEnvironment {
  constructor(config, context) {
    super(config, context);

    // Inject Node.js Fetch API globals into jsdom window.
    // Node v18+ has these built-in on `globalThis`.
    const nodeFetch = {
      fetch: globalThis.fetch,
      Response: globalThis.Response,
      Request: globalThis.Request,
      Headers: globalThis.Headers,
      TextEncoder: globalThis.TextEncoder,
      TextDecoder: globalThis.TextDecoder,
      ReadableStream: globalThis.ReadableStream,
      WritableStream: globalThis.WritableStream,
      TransformStream: globalThis.TransformStream,
      BroadcastChannel: globalThis.BroadcastChannel,
    };

    for (const [key, value] of Object.entries(nodeFetch)) {
      if (value !== undefined && this.global[key] === undefined) {
        this.global[key] = value;
      }
    }
  }
}

module.exports = JSDOMEnvironmentWithFetch;
