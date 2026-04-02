import type { Config } from "jest";

const config: Config = {
  preset: "ts-jest",
  testEnvironment: "<rootDir>/jest-env-with-fetch.js",
  testEnvironmentOptions: {},
  setupFiles: ["<rootDir>/src/__tests__/msw/jest.setup.ts"],
  setupFilesAfterEnv: ["@testing-library/jest-dom"],
  moduleNameMapper: {
    "^@/(.*)$": "<rootDir>/src/$1",
    "\\.(css|less|scss|sass)$": "<rootDir>/src/__tests__/__mocks__/styleMock.js",
    "\\.(gif|ttf|eot|svg|png)$": "<rootDir>/src/__tests__/__mocks__/fileMock.js",
    "^react-markdown$": "<rootDir>/src/__tests__/__mocks__/react-markdown.js",
    "^rehype-highlight$": "<rootDir>/src/__tests__/__mocks__/rehype-highlight.js",
    "^remark-gfm$": "<rootDir>/src/__tests__/__mocks__/remark-gfm.js",
    "^lightweight-charts$": "<rootDir>/src/__tests__/__mocks__/lightweight-charts.js",
    "^until-async$": "<rootDir>/src/__tests__/__mocks__/until-async.cjs",
    "^msw/node$": "<rootDir>/node_modules/msw/lib/node/index.js",
    "^@mswjs/interceptors$": "<rootDir>/node_modules/@mswjs/interceptors/lib/node/index.cjs",
    "^@mswjs/interceptors/ClientRequest$": "<rootDir>/node_modules/@mswjs/interceptors/lib/node/interceptors/ClientRequest/index.cjs",
    "^@mswjs/interceptors/XMLHttpRequest$": "<rootDir>/node_modules/@mswjs/interceptors/lib/node/interceptors/XMLHttpRequest/index.cjs",
    "^@mswjs/interceptors/fetch$": "<rootDir>/node_modules/@mswjs/interceptors/lib/node/interceptors/fetch/index.cjs",
    "^@mswjs/interceptors/RemoteHttpInterceptor$": "<rootDir>/node_modules/@mswjs/interceptors/lib/node/RemoteHttpInterceptor.cjs",
    "^@mswjs/interceptors/presets/node$": "<rootDir>/node_modules/@mswjs/interceptors/lib/node/presets/node.cjs",
  },
  testMatch: ["<rootDir>/src/**/*.test.ts", "<rootDir>/src/**/*.test.tsx"],
  transform: {
    "^.+\\.(ts|tsx)$": [
      "ts-jest",
      {
        tsconfig: {
          jsx: "react-jsx",
          esModuleInterop: true,
          moduleResolution: "node",
          module: "commonjs",
        },
      },
    ],
  },
};

export default config;
