/** @type {import('tailwindcss').Config} */

/*
 * AnnaData's design system.
 *
 * `theme.extend` was empty, so every colour in this app was an ad-hoc hex or a
 * stock Tailwind grey chosen a component at a time. The brand was an accident.
 * This file makes it a decision.
 *
 * Three things drive every value below, and none of them is taste:
 *
 * 1. THE SCREEN IS OUTDOORS. A farmer reads this on a budget Android in direct
 *    sunlight, often through a scratched protector. Stock `gray-400` on white
 *    is 3.66:1 - legible in an office, gone in a field. Every colour here that
 *    is allowed to carry text is at least 4.5:1 on white, and the ratios are
 *    written next to each one so the next person does not have to re-measure.
 *
 * 2. THE TEXT IS BIGGER THAN THE WEB'S DEFAULT. `base` is 17px, not 16px, and
 *    the whole scale is shifted up with it. This intentionally changes every
 *    existing `text-sm`/`text-lg` in the app. Small type is the single most
 *    common way an interface excludes an older reader, and a lot of this
 *    product's users are over fifty.
 *
 * 3. IT IS A TOUCHSCREEN. There is no cursor and no hover. `spacing.touch` is
 *    44px because that is the smallest target a thumb hits reliably, and it is
 *    named rather than numbered so that using it is easier than not.
 *
 * The greys are warm (a little yellow-red in them) rather than the blue-tinted
 * stock Tailwind greys. Next to green and next to soil in a photograph, cold
 * grey reads as clinical; warm grey reads as paper.
 */
module.exports = {
  content: ["./src/**/*.{js,jsx,ts,tsx}"],
  theme: {
    extend: {
      colors: {
        /*
         * Leaf - the primary. Standing crop, and the colour of a confirmed,
         * sourced answer. 600 and darker are safe for text on white.
         */
        leaf: {
          50: "#F0F7F1",
          100: "#DBEDE0",
          200: "#B8DBC3",
          300: "#8AC29E",
          400: "#55A277",
          500: "#2E8557",
          600: "#1F6B45", //  6.47:1 on white - AA for all text
          700: "#1A5638", //  8.63:1 on white
          800: "#16452E", // 10.91:1 on white
          900: "#123826",
        },

        /*
         * Grain - ripe wheat. The accent, used for money: prices, MSP, rates.
         * Deliberately narrow in use. If everything is highlighted, the price
         * is not.
         */
        grain: {
          50: "#FEF8EC",
          100: "#FBEBC8",
          200: "#F6D68E",
          300: "#EFBB4E",
          400: "#E5A21F",
          500: "#C98410",
          600: "#A2650C", // 4.77:1 on white - AA, but only just
          700: "#7C4D0E", // 7.18:1 on white
          800: "#663F10", // 8.69:1 on grain-50
          900: "#56350F",
        },

        /*
         * Soil - the neutrals. Text, borders, surfaces.
         *
         * Note the cutoff: 500 and darker may carry text; 400 and lighter may
         * NOT. 400 is 3.66:1, which fails AA for body text. It exists for
         * borders, rules and disabled states only.
         */
        soil: {
          50: "#F7F6F3", // page and answer-card surface
          100: "#EDEBE6",
          200: "#DAD6CD", // default border
          300: "#B8B2A5",
          400: "#8C8577", // 3.66:1 - NOT for text
          500: "#6B6558", // 5.79:1 - the lightest text tone allowed
          600: "#524D42", // 8.40:1 - secondary text
          700: "#3D392F", // 11.51:1
          800: "#2A2721", // 14.89:1 - body text
          900: "#1A1815", // 17.72:1 - headings
        },

        /*
         * Register - the CIB&RC pesticide register, and only that.
         *
         * A dose that came out of the statutory register is the highest-trust
         * thing this product ever says, and an answer that declines to name one
         * because the crop-pest pair is not in the register is the second. Both
         * get this colour, because both are the register speaking. It is
         * deliberately not red: a refusal is the system working, not an error.
         */
        register: {
          50: "#F2F6FA",
          100: "#E1EAF3",
          200: "#C3D5E6",
          600: "#2C5578", // 7.11:1 on white
          700: "#234462",
          800: "#1B3549",
        },
      },

      fontFamily: {
        /*
         * Kept in sync with --font-app in index.css, which is where the
         * reasoning about script coverage and ordering lives.
         */
        sans: [
          "Outfit",
          "Noto Sans Devanagari",
          "Noto Sans Gurmukhi",
          "Noto Sans Bengali",
          "system-ui",
          "-apple-system",
          "Segoe UI",
          "sans-serif",
        ],
      },

      /*
       * The type scale, shifted up one step from stock Tailwind.
       *
       * Line heights are generous throughout because Devanagari and Gurmukhi
       * need the room: matras sit above the headline and below the baseline, and
       * at Tailwind's default 1.5 a two-line Hindi paragraph collides with
       * itself. What looks airy in English is merely correct in Devanagari.
       */
      fontSize: {
        xs: ["0.8125rem", { lineHeight: "1.5" }], // 13px - labels only
        sm: ["0.9375rem", { lineHeight: "1.6" }], // 15px
        base: ["1.0625rem", { lineHeight: "1.75" }], // 17px - body
        lg: ["1.1875rem", { lineHeight: "1.7" }], // 19px
        xl: ["1.375rem", { lineHeight: "1.55" }], // 22px
        "2xl": ["1.625rem", { lineHeight: "1.4" }], // 26px
        "3xl": ["2rem", { lineHeight: "1.3" }], // 32px
        "4xl": ["2.5rem", { lineHeight: "1.2" }], // 40px
      },

      spacing: {
        touch: "2.75rem", // 44px - minimum tap target
        "touch-lg": "3.5rem", // 56px - voice and camera, the primary inputs
      },
      minHeight: { touch: "2.75rem", "touch-lg": "3.5rem" },
      minWidth: { touch: "2.75rem", "touch-lg": "3.5rem" },

      borderRadius: { card: "1rem", pill: "9999px" },

      /*
       * One shadow, soft and cheap. Layered shadows and blurs cost compositing
       * work on a phone that has none to spare.
       */
      boxShadow: {
        card: "0 1px 2px rgba(26, 24, 21, 0.06), 0 2px 8px rgba(26, 24, 21, 0.05)",
        lift: "0 2px 4px rgba(26, 24, 21, 0.08), 0 8px 20px rgba(26, 24, 21, 0.08)",
      },

      // The narrowest phone worth designing for, named so it can be tested.
      screens: { xs: "360px" },

      keyframes: {
        // The pending state. See .thinking-* in index.css.
        sprout: {
          "0%, 100%": { transform: "scaleY(0.4)", opacity: "0.45" },
          "50%": { transform: "scaleY(1)", opacity: "1" },
        },
      },
      animation: { sprout: "sprout 1.1s ease-in-out infinite" },
    },
  },
  plugins: [],
};
