import type { SVGProps } from "react";

type Props = SVGProps<SVGSVGElement> & { size?: number };

const base = (size: number, props: SVGProps<SVGSVGElement>) => ({
  width: size,
  height: size,
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.8,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
  ...props
});

export const SearchIcon = ({ size = 14, ...props }: Props) => (
  <svg {...base(size, props)} strokeWidth={2}>
    <circle cx="11" cy="11" r="7" />
    <path d="m21 21-4.3-4.3" />
  </svg>
);

export const LibraryIcon = ({ size = 14, ...props }: Props) => (
  <svg {...base(size, props)}>
    <rect x="3" y="3" width="7" height="7" rx="1" />
    <rect x="14" y="3" width="7" height="7" rx="1" />
    <rect x="3" y="14" width="7" height="7" rx="1" />
    <rect x="14" y="14" width="7" height="7" rx="1" />
  </svg>
);

export const UploadIcon = ({ size = 14, ...props }: Props) => (
  <svg {...base(size, props)}>
    <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
    <polyline points="17 8 12 3 7 8" />
    <line x1="12" y1="3" x2="12" y2="15" />
  </svg>
);

export const ChatIcon = ({ size = 14, ...props }: Props) => (
  <svg {...base(size, props)}>
    <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
  </svg>
);

export const CampaignsIcon = ({ size = 14, ...props }: Props) => (
  <svg {...base(size, props)}>
    <path d="M3 11l18-5v12l-18-5z" />
    <path d="M11.6 16.8a3 3 0 1 1-5.8-1.6" />
  </svg>
);

export const SettingsIcon = ({ size = 14, ...props }: Props) => (
  <svg {...base(size, props)}>
    <circle cx="12" cy="12" r="3" />
    <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
  </svg>
);

export const PlusIcon = ({ size = 13, ...props }: Props) => (
  <svg {...base(size, props)} strokeWidth={2.2}>
    <path d="M12 5v14M5 12h14" />
  </svg>
);

export const DownloadIcon = ({ size = 13, ...props }: Props) => (
  <svg {...base(size, props)} strokeWidth={2}>
    <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
    <polyline points="7 10 12 15 17 10" />
    <line x1="12" y1="15" x2="12" y2="3" />
  </svg>
);

export const SendIcon = ({ size = 14, ...props }: Props) => (
  <svg {...base(size, props)} strokeWidth={2}>
    <line x1="22" y1="2" x2="11" y2="13" />
    <polygon points="22 2 15 22 11 13 2 9 22 2" />
  </svg>
);

export const StopIcon = ({ size = 12, ...props }: Props) => (
  <svg {...base(size, props)} fill="currentColor" stroke="none">
    <rect x="6" y="6" width="12" height="12" rx="1.5" />
  </svg>
);

export const CopyIcon = ({ size = 11, ...props }: Props) => (
  <svg {...base(size, props)} strokeWidth={2}>
    <rect x="9" y="9" width="13" height="13" rx="2" />
    <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
  </svg>
);

export const CloseIcon = ({ size = 14, ...props }: Props) => (
  <svg {...base(size, props)} strokeWidth={2}>
    <path d="M18 6 6 18M6 6l12 12" />
  </svg>
);

export const ChevronRightIcon = ({ size = 10, ...props }: Props) => (
  <svg {...base(size, props)} strokeWidth={2.4}>
    <polyline points="9 18 15 12 9 6" />
  </svg>
);

export const ChevronDownIcon = ({ size = 11, ...props }: Props) => (
  <svg {...base(size, props)} strokeWidth={2.4}>
    <polyline points="6 9 12 15 18 9" />
  </svg>
);

export const CheckIcon = ({ size = 13, ...props }: Props) => (
  <svg {...base(size, props)} strokeWidth={2.4}>
    <polyline points="20 6 9 17 4 12" />
  </svg>
);

export const XIcon = ({ size = 11, ...props }: Props) => (
  <svg {...base(size, props)} strokeWidth={2.4}>
    <path d="M18 6 6 18M6 6l12 12" />
  </svg>
);

export const AlertIcon = ({ size = 14, ...props }: Props) => (
  <svg {...base(size, props)} strokeWidth={2}>
    <path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
    <line x1="12" y1="9" x2="12" y2="13" />
    <line x1="12" y1="17" x2="12.01" y2="17" />
  </svg>
);

export const ShieldIcon = ({ size = 14, ...props }: Props) => (
  <svg {...base(size, props)} strokeWidth={2}>
    <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
  </svg>
);

export const PlayIcon = ({ size = 14, ...props }: Props) => (
  <svg {...base(size, props)} fill="currentColor" stroke="none">
    <polygon points="6 4 20 12 6 20 6 4" />
  </svg>
);

export const TrashIcon = ({ size = 12, ...props }: Props) => (
  <svg {...base(size, props)} strokeWidth={2}>
    <polyline points="3 6 5 6 21 6" />
    <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" />
    <path d="M10 11v6M14 11v6" />
  </svg>
);

export const EditIcon = ({ size = 12, ...props }: Props) => (
  <svg {...base(size, props)} strokeWidth={2}>
    <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" />
    <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" />
  </svg>
);

export const SparkleIcon = ({ size = 12, ...props }: Props) => (
  <svg {...base(size, props)} fill="currentColor" stroke="none">
    <path d="M12 2 13.5 8.5 20 10l-6.5 1.5L12 18l-1.5-6.5L4 10l6.5-1.5z" />
  </svg>
);

export const FlowIcon = ({ size = 13, ...props }: Props) => (
  <svg {...base(size, props)} strokeWidth={1.9}>
    <polyline points="22 12 18 12 15 21 9 3 6 12 2 12" />
  </svg>
);

export const LayersIcon = ({ size = 13, ...props }: Props) => (
  <svg {...base(size, props)} strokeWidth={1.9}>
    <polygon points="12 2 2 7 12 12 22 7 12 2" />
    <polyline points="2 17 12 22 22 17" />
    <polyline points="2 12 12 17 22 12" />
  </svg>
);

export const FilmIcon = ({ size = 14, ...props }: Props) => (
  <svg {...base(size, props)}>
    <rect x="2" y="2" width="20" height="20" rx="2.18" />
    <line x1="7" y1="2" x2="7" y2="22" />
    <line x1="17" y1="2" x2="17" y2="22" />
    <line x1="2" y1="12" x2="22" y2="12" />
    <line x1="2" y1="7" x2="7" y2="7" />
    <line x1="2" y1="17" x2="7" y2="17" />
    <line x1="17" y1="17" x2="22" y2="17" />
    <line x1="17" y1="7" x2="22" y2="7" />
  </svg>
);

export const InfoIcon = ({ size = 11, ...props }: Props) => (
  <svg {...base(size, props)} strokeWidth={2}>
    <circle cx="12" cy="12" r="10" />
    <line x1="12" y1="16" x2="12" y2="12" />
    <line x1="12" y1="8" x2="12.01" y2="8" />
  </svg>
);

export const GraphIcon = ({ size = 14, ...props }: Props) => (
  <svg {...base(size, props)} strokeWidth={1.9}>
    <circle cx="5" cy="6" r="2.5" />
    <circle cx="19" cy="6" r="2.5" />
    <circle cx="12" cy="19" r="2.5" />
    <line x1="7" y1="7.5" x2="10" y2="17" />
    <line x1="17" y1="7.5" x2="14" y2="17" />
    <line x1="7.5" y1="6" x2="16.5" y2="6" />
  </svg>
);

export const BenchmarkIcon = ({ size = 14, ...props }: Props) => (
  <svg {...base(size, props)} strokeWidth={1.9}>
    <path d="M4 19V5" />
    <path d="M4 19h16" />
    <rect x="7" y="12" width="3" height="4" rx="0.6" />
    <rect x="12" y="8" width="3" height="8" rx="0.6" />
    <rect x="17" y="4" width="3" height="12" rx="0.6" />
  </svg>
);

export const CubeIcon = ({ size = 14, ...props }: Props) => (
  <svg {...base(size, props)} strokeWidth={1.8}>
    <path d="M12 2L3 7v10l9 5 9-5V7z" />
    <line x1="12" y1="2" x2="12" y2="22" />
    <line x1="3" y1="7" x2="21" y2="7" />
  </svg>
);
