import "@testing-library/jest-dom/vitest";
import { vi, afterEach } from "vitest";
import { cleanup } from "@testing-library/react";
import { readFileSync } from "node:fs";
import { initializeLocale } from "../src/app/i18n";
await initializeLocale(
  JSON.parse(readFileSync("public/locales/en.json", "utf8")),
);
export class TestEvents extends EventTarget {
  static instances: TestEvents[] = [];
  readyState = 0;
  onopen: ((event: Event) => void) | null = null;
  onerror: ((event: Event) => void) | null = null;
  url: string;
  constructor(url: string) {
    super();
    this.url = url;
    TestEvents.instances.push(this);
  }
  close() {
    this.readyState = 2;
  }
  open() {
    this.readyState = 1;
    this.onopen?.(new Event("open"));
  }
  change(data: object) {
    this.dispatchEvent(
      new MessageEvent("change", { data: JSON.stringify(data) }),
    );
  }
  fail() {
    this.onerror?.(new Event("error"));
  }
}
Object.defineProperty(window, "matchMedia", {
  writable: true,
  value: (query: string) => ({
    matches: false,
    media: query,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    addListener: vi.fn(),
    removeListener: vi.fn(),
    dispatchEvent: vi.fn(),
  }),
});
vi.stubGlobal("EventSource", TestEvents);
vi.stubGlobal(
  "ResizeObserver",
  class {
    observe() {}
    unobserve() {}
    disconnect() {}
  },
);
if (!CSS.escape)
  CSS.escape = (value: string) => value.replace(/["\\]/g, "\\$&");
if (!Element.prototype.scrollIntoView)
  Element.prototype.scrollIntoView = () => {};
afterEach(() => {
  cleanup();
  TestEvents.instances = [];
  vi.useRealTimers();
});
