import type { SVGProps } from "react";

const base: SVGProps<SVGSVGElement> = {
  viewBox: "0 0 20 20",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.5,
  strokeLinecap: "round",
  strokeLinejoin: "round",
  "aria-hidden": true,
};

export const Check = (p: SVGProps<SVGSVGElement>) => (
  <svg {...base} {...p}>
    <circle cx="10" cy="10" r="8" />
    <path d="M6.5 10.5l2.5 2.5 4.5-5" />
  </svg>
);
export const Cross = (p: SVGProps<SVGSVGElement>) => (
  <svg {...base} {...p}>
    <rect x="2.5" y="2.5" width="15" height="15" rx="3" />
    <path d="M7 7l6 6M13 7l-6 6" />
  </svg>
);
export const Dash = (p: SVGProps<SVGSVGElement>) => (
  <svg {...base} {...p}>
    <circle cx="10" cy="10" r="8" />
    <path d="M6.5 10h7" />
  </svg>
);
export const Close = (p: SVGProps<SVGSVGElement>) => (
  <svg {...base} {...p}>
    <path d="M5 5l10 10M15 5L5 15" />
  </svg>
);
export const Upload = (p: SVGProps<SVGSVGElement>) => (
  <svg {...base} {...p}>
    <path d="M10 13V3.5M6.5 7L10 3.5 13.5 7M3.5 13v3h13v-3" />
  </svg>
);
export const Arrow = (p: SVGProps<SVGSVGElement>) => (
  <svg {...base} {...p}>
    <path d="M4 10h12M11 5l5 5-5 5" />
  </svg>
);
export const Download = (p: SVGProps<SVGSVGElement>) => (
  <svg {...base} {...p}>
    <path d="M10 3.5V13M6.5 9.5L10 13l3.5-3.5M3.5 13v3h13v-3" />
  </svg>
);

export function Logo({ size = 28 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden="true">
      <rect width="32" height="32" rx="9" fill="#0F5C58" />
      <path
        d="M9 16.5l4.5 4.5L23 11"
        fill="none"
        stroke="#FBF9F5"
        strokeWidth="2.6"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}
export const Broken = (p: SVGProps<SVGSVGElement>) => (
  <svg {...base} {...p}>
    <rect x="2.5" y="2.5" width="15" height="15" rx="3" />
    <path d="M10 2.5l-2 5 4 2-2 5 0 3" />
  </svg>
);
