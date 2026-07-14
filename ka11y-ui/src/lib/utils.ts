import { type ClassValue, clsx } from "clsx";
import { extendTailwindMerge } from "tailwind-merge";

// Registers the brand type scale (text-h1..h3, text-p1..p4) under the
// font-size group so it doesn't collide with text-color utilities like
// text-white (tailwind-merge can't infer custom theme keys on its own).
const customTwMerge = extendTailwindMerge({
  extend: {
    classGroups: {
      "font-size": [{ text: ["h1", "h2", "h3", "p1", "p2", "p3", "p4"] }],
    },
  },
});

export function cn(...inputs: ClassValue[]) {
  return customTwMerge(clsx(inputs));
}
