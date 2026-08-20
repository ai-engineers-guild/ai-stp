import "@testing-library/jest-dom/vitest";

import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

// Testing Library auto-cleanup hooks itself onto a global `afterEach`, which
// only exists when vitest runs with `globals: true`. This project keeps globals
// off, so without this the DOM accumulates across tests in a file and role
// queries start matching leftovers from an earlier render.
afterEach(cleanup);
