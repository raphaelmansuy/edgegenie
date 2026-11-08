/** Ambient types for imports Vite resolves.
 *
 * The project has no `vite/client` types (the tsconfig does not include them), so importing a `.css`
 * file — which KaTeX's stylesheet requires — was a type error. Declaring the module here keeps the
 * build honest without pulling in the whole Vite type surface.
 */
declare module "*.css";
