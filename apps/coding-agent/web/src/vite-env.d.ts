/** Ambient types for imports Vite resolves.
 *
 * The project has no `vite/client` types (the tsconfig does not include them), so importing a `.css`
 * file — which KaTeX's stylesheet requires — was a type error. Declaring the module here keeps the
 * build honest without pulling in the whole Vite type surface.
 */
declare module "*.css";

/** Build-time facts substituted by `define` in `vite.config.ts`. They are strings, always present in
 *  a Vite build and in a Vitest run (the test setup assigns them), so a component can read them
 *  without a guard — but a fallback is declared here anyway, because TypeScript cannot see the
 *  substitution and an `undefined` in a version label is the kind of thing that ships. */
declare const __APP_VERSION__: string;
declare const __APP_COMMIT__: string;
declare const __APP_BUILT__: string;
