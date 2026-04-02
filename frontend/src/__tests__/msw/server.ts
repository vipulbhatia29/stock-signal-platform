/**
 * MSW Node server — used in Jest (Node / jsdom) test environment.
 *
 * Import { server } in tests that need to override handlers at runtime, e.g.:
 *
 *   import { server } from "@/__tests__/msw/server";
 *   server.use(http.get("/api/v1/portfolio/summary", () => HttpResponse.json({ ... })));
 */

import { setupServer } from "msw/node";
import { handlers } from "./handlers";

export const server = setupServer(...handlers);
