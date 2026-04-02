// Jest automatic mock for next/navigation — applies globally to all tests.
// Located in __mocks__/next/ (rootDir sibling) so Jest auto-resolves it.
// Other project mocks live in src/__tests__/__mocks__/ via moduleNameMapper.
export const useRouter = jest.fn(() => ({
  push: jest.fn(),
  replace: jest.fn(),
  back: jest.fn(),
  forward: jest.fn(),
  refresh: jest.fn(),
  prefetch: jest.fn(),
}));

export const usePathname = jest.fn(() => "/");
export const useSearchParams = jest.fn(() => new URLSearchParams());
export const useParams = jest.fn(() => ({}));
export const redirect = jest.fn();
export const notFound = jest.fn();
