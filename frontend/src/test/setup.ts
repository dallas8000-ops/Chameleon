// jsdom replaces the global AbortSignal, but Node's fetch `Request` (used by React Router's data
// routers for navigations) only accepts Node's own AbortSignal. Drop signals passed to Request in
// tests; no route loaders/actions rely on aborting here. App fetches are mocked and unaffected.
const NodeRequest = globalThis.Request;

class TestRequest extends NodeRequest {
  constructor(input: RequestInfo | URL, init?: RequestInit) {
    const { signal: _signal, ...rest } = init ?? {};
    super(input, rest);
  }
}

globalThis.Request = TestRequest as typeof Request;
