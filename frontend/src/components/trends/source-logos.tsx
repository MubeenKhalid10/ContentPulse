import {
  CpuIcon,
  GlobeIcon,
  type LucideIcon,
  NewspaperIcon,
  RadarIcon,
  SearchIcon,
} from "lucide-react";

/**
 * Small marks that identify each provider in source lists. Simplified
 * drawings in the providers' colors, not their official artwork; providers
 * without a mark get a neutral icon.
 */

type Mark = () => React.ReactElement;

const GoogleTrends: Mark = () => (
  <svg viewBox="0 0 32 32" className="size-7">
    <path
      d="M5 22 L12 15 L17 19 L26 9"
      fill="none"
      strokeWidth="3.2"
      strokeLinecap="round"
      strokeLinejoin="round"
      stroke="url(#gt-line)"
    />
    <path d="M21 8.5 H26.5 V14" fill="none" stroke="#34A853" strokeWidth="3.2" strokeLinecap="round" strokeLinejoin="round" />
    <defs>
      <linearGradient id="gt-line" x1="5" y1="0" x2="26" y2="0" gradientUnits="userSpaceOnUse">
        <stop offset="0" stopColor="#4285F4" />
        <stop offset="0.4" stopColor="#EA4335" />
        <stop offset="0.7" stopColor="#FBBC04" />
        <stop offset="1" stopColor="#34A853" />
      </linearGradient>
    </defs>
  </svg>
);

const GoogleNews: Mark = () => (
  <svg viewBox="0 0 32 32" className="size-7">
    <rect x="7" y="4" width="20" height="14" rx="2" fill="#34A853" transform="rotate(8 17 11)" />
    <rect x="5" y="5" width="20" height="14" rx="2" fill="#EA4335" transform="rotate(-8 15 12)" />
    <rect x="3" y="9" width="26" height="18" rx="2.5" fill="#4285F4" />
    <text x="9.5" y="22.5" fontSize="11" fontWeight="700" fontFamily="Arial, sans-serif" fill="#fff">
      G
    </text>
    <rect x="18" y="14" width="8" height="2" rx="1" fill="#fff" />
    <rect x="18" y="18" width="8" height="2" rx="1" fill="#fff" />
    <rect x="18" y="22" width="6" height="2" rx="1" fill="#fff" />
  </svg>
);

const Reddit: Mark = () => (
  <svg viewBox="0 0 32 32" className="size-7">
    <circle cx="16" cy="16" r="14" fill="#FF4500" />
    <ellipse cx="16" cy="18.5" rx="8" ry="5.5" fill="#fff" />
    <circle cx="23" cy="8" r="1.8" fill="#fff" />
    <path d="M16 13 L17.5 7.5 L23 8" fill="none" stroke="#fff" strokeWidth="1.2" />
    <circle cx="13" cy="18" r="1.4" fill="#FF4500" />
    <circle cx="19" cy="18" r="1.4" fill="#FF4500" />
    <path d="M13 21 Q16 23 19 21" fill="none" stroke="#FF4500" strokeWidth="1.1" strokeLinecap="round" />
  </svg>
);

const HackerNews: Mark = () => (
  <svg viewBox="0 0 32 32" className="size-7">
    <rect x="3" y="3" width="26" height="26" rx="3" fill="#FF6600" />
    <path d="M10 9 L16 17.5 L22 9 M16 17.5 V24" fill="none" stroke="#fff" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);

const Rss: Mark = () => (
  <svg viewBox="0 0 32 32" className="size-7">
    <rect x="3" y="3" width="26" height="26" rx="6" fill="#F26522" />
    <circle cx="10.5" cy="21.5" r="2.4" fill="#fff" />
    <path d="M9 14.5a8.5 8.5 0 0 1 8.5 8.5 M9 8.5a14.5 14.5 0 0 1 14.5 14.5" fill="none" stroke="#fff" strokeWidth="2.6" strokeLinecap="round" />
  </svg>
);

const X: Mark = () => (
  <svg viewBox="0 0 32 32" className="size-7">
    <rect x="3" y="3" width="26" height="26" rx="6" fill="#000" />
    <path d="M10 9 L22 23 M22 9 L10 23" stroke="#fff" strokeWidth="2.4" strokeLinecap="round" />
  </svg>
);

const Instagram: Mark = () => (
  <svg viewBox="0 0 32 32" className="size-7">
    <defs>
      <linearGradient id="ig-bg" x1="0" y1="1" x2="1" y2="0">
        <stop offset="0" stopColor="#FEDA75" />
        <stop offset="0.35" stopColor="#FA7E1E" />
        <stop offset="0.6" stopColor="#D62976" />
        <stop offset="1" stopColor="#4F5BD5" />
      </linearGradient>
    </defs>
    <rect x="3" y="3" width="26" height="26" rx="7.5" fill="url(#ig-bg)" />
    <rect x="9" y="9" width="14" height="14" rx="4.5" fill="none" stroke="#fff" strokeWidth="2" />
    <circle cx="16" cy="16" r="3.3" fill="none" stroke="#fff" strokeWidth="2" />
    <circle cx="20.3" cy="11.7" r="1" fill="#fff" />
  </svg>
);

const LinkedIn: Mark = () => (
  <svg viewBox="0 0 32 32" className="size-7">
    <rect x="3" y="3" width="26" height="26" rx="4" fill="#0A66C2" />
    <rect x="8.5" y="13" width="3.4" height="10" fill="#fff" />
    <circle cx="10.2" cy="9.6" r="2" fill="#fff" />
    <path d="M15 13 H18.2 V14.6 C19 13.3 20.3 12.8 21.6 12.8 C24 12.8 24.5 14.5 24.5 16.8 V23 H21.1 V17.6 C21.1 16.4 20.9 15.6 19.8 15.6 C18.7 15.6 18.4 16.4 18.4 17.6 V23 H15 Z" fill="#fff" />
  </svg>
);

const MARKS: Record<string, Mark> = {
  google_trends: GoogleTrends,
  google_news: GoogleNews,
  reddit: Reddit,
  hacker_news: HackerNews,
  rss: Rss,
  x: X,
  instagram: Instagram,
  linkedin: LinkedIn,
};

const ICONS: Record<string, LucideIcon> = {
  google_trends_tech: CpuIcon,
  exa: SearchIcon,
};

export function SourceLogo({ sourceKey }: { sourceKey: string }) {
  const MarkFor = MARKS[sourceKey];
  if (MarkFor) return <MarkFor />;
  const Icon = ICONS[sourceKey] ?? (sourceKey.includes("news") ? NewspaperIcon : sourceKey.includes("api") ? GlobeIcon : RadarIcon);
  return <Icon className="size-5 text-muted-foreground" />;
}
