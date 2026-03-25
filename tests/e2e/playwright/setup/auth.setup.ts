import { test as setup } from "@playwright/test";

const AUTH_FILE = ".auth/user.json";

setup("authenticate", async ({ request }) => {
  // Register a test user (ignore if already exists)
  await request.post("http://localhost:8181/api/v1/auth/register", {
    data: {
      email: "e2e@test.com",
      password: "TestPass1!",
    },
  });

  // Login to get JWT cookie
  const loginResponse = await request.post(
    "http://localhost:8181/api/v1/auth/login",
    {
      data: {
        email: "e2e@test.com",
        password: "TestPass1!",
      },
    }
  );

  // Save storage state (cookies + localStorage)
  await request.storageState({ path: AUTH_FILE });
});
