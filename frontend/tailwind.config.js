import typography from "@tailwindcss/typography";

/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{vue,ts,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      typography: {
        // Brand tweaks for the `prose` class used by HelpView.
        // Links pick up the Aracne indigo; inline code gets a
        // subtle background rather than the browser default.
        DEFAULT: {
          css: {
            a: {
              color: "rgb(79 70 229)", // indigo-600
              textDecoration: "none",
              fontWeight: "500",
            },
            "a:hover": {
              textDecoration: "underline",
            },
            code: {
              backgroundColor: "rgb(243 244 246)", // gray-100
              color: "rgb(17 24 39)", // gray-900
              padding: "0.125rem 0.375rem",
              borderRadius: "0.25rem",
              fontWeight: "400",
            },
            // markdown_it emits bare <code>; strip the
            // default backticks the typography plugin adds.
            "code::before": { content: '""' },
            "code::after": { content: '""' },
          },
        },
        invert: {
          css: {
            a: { color: "rgb(165 180 252)" }, // indigo-300 on dark
            code: {
              backgroundColor: "rgb(31 41 55)", // gray-800
              color: "rgb(229 231 235)", // gray-200
            },
          },
        },
      },
    },
  },
  plugins: [typography],
};
