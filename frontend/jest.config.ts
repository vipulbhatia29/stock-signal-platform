import type { Config } from "jest";

const config: Config = {
  preset: "ts-jest",
  testEnvironment: "jest-environment-jsdom",
  setupFilesAfterEnv: ["@testing-library/jest-dom"],
  moduleNameMapper: {
    "^@/(.*)$": "<rootDir>/src/$1",
    "\\.(css|less|scss|sass)$": "<rootDir>/src/__tests__/__mocks__/styleMock.js",
    "\\.(gif|ttf|eot|svg|png)$": "<rootDir>/src/__tests__/__mocks__/fileMock.js",
    "^react-markdown$": "<rootDir>/src/__tests__/__mocks__/react-markdown.js",
    "^rehype-highlight$": "<rootDir>/src/__tests__/__mocks__/rehype-highlight.js",
    "^remark-gfm$": "<rootDir>/src/__tests__/__mocks__/remark-gfm.js",
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
