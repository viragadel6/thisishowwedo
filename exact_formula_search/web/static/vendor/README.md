# Vendored browser libraries

These files are shipped as-is so the interface runs fully offline from the same
origin as the API, without a bundler step and without any third-party CDN.

| Directory | Version | License | Files |
| --- | --- | --- | --- |
| `react/` | 18.3.1 | MIT (`react/LICENSE`) | `react.production.min.js` |
| `react-dom/` | 18.3.1 | MIT (`react-dom/LICENSE`) | `react-dom.production.min.js` |
| `katex/` | 0.16.11 | MIT (`katex/LICENSE`) | `katex.min.js`, `katex.min.css`, `fonts/*.woff2`, `package.json` |

Sources were taken from the published npm tarballs of the exact versions above
(`npm pack react@18.3.1 react-dom@18.3.1 katex@0.16.11`). Nothing else is
vendored; the application code in `../js/` is part of this repository and is
compiled from `../../jsx/` by `../../jsx/build.mjs`.

Font files are limited to the `woff2` set that `katex.min.css` references.
