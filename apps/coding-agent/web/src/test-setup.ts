import "@testing-library/jest-dom/vitest";

/** The build facts `vite.config.ts` substitutes at build time.
 *
 *  A Vitest run does compile the config, but the substitution is only applied to modules Vite
 *  transforms — a `typeof __APP_VERSION__` guard would then be false, and every test would see a
 *  version of `unknown`. Assigning them here makes the test run see what a build sees, and pins them
 *  so an assertion can name one exact string. */
(globalThis as Record<string, unknown>).__APP_VERSION__ = "1.0.0";
(globalThis as Record<string, unknown>).__APP_COMMIT__ = "abc1234";
(globalThis as Record<string, unknown>).__APP_BUILT__ = "2026-11-11T00:00:00.000Z";
