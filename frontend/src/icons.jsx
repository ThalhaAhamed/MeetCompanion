// Shared inline line-icon set — keeps every icon in the app visually consistent
// (18px viewBox, 1.6 stroke, currentColor) instead of mixing unicode glyphs.

export const RocketIcon = (props) => (
  <svg viewBox="0 0 18 18" width="15" height="15" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" {...props}>
    <path d="M9 2c2 1 3.5 3 3.5 6.5S9 15 9 15s-3.5-3-3.5-6.5S7 3 9 2Z" />
    <circle cx="9" cy="7.5" r="1.3" />
    <path d="M6 11.5 3.5 14M12 11.5 14.5 14M7 15l-.5 1.5M11 15l.5 1.5" />
  </svg>
)

export const UploadIcon = (props) => (
  <svg viewBox="0 0 18 18" width="13" height="13" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" {...props}>
    <path d="M9 12V3M5.5 6.5 9 3l3.5 3.5" />
    <path d="M3 12.5v1.3a1.7 1.7 0 0 0 1.7 1.7h8.6a1.7 1.7 0 0 0 1.7-1.7v-1.3" />
  </svg>
)

export const CalendarIcon = (props) => (
  <svg viewBox="0 0 18 18" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" {...props}>
    <rect x="2.5" y="3.5" width="13" height="12" rx="2.2" />
    <path d="M2.5 7h13M6 2v3M12 2v3" />
  </svg>
)

export const SearchIcon = (props) => (
  <svg viewBox="0 0 18 18" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" {...props}>
    <circle cx="8" cy="8" r="5.2" />
    <path d="M15.5 15.5 12 12" />
  </svg>
)

export const InboxIcon = (props) => (
  <svg viewBox="0 0 40 40" width="34" height="34" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" {...props}>
    <path d="M8 20 12 8h16l4 12" />
    <path d="M8 20v10a2 2 0 0 0 2 2h20a2 2 0 0 0 2-2V20h-8a4 4 0 0 1-8 0H8Z" />
  </svg>
)

export const CursorClickIcon = (props) => (
  <svg viewBox="0 0 40 40" width="34" height="34" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" {...props}>
    <path d="M14 8 14 26 19 21.5 22.5 29 26 27.5 22.5 20 28.5 20 14 8Z" />
  </svg>
)

export const CheckCircleIcon = (props) => (
  <svg viewBox="0 0 14 14" width="11" height="11" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" {...props}>
    <circle cx="7" cy="7" r="5.6" />
    <path d="M4.6 7.1 6.2 8.7 9.4 5.3" />
  </svg>
)

export const XCircleIcon = (props) => (
  <svg viewBox="0 0 14 14" width="11" height="11" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" {...props}>
    <circle cx="7" cy="7" r="5.6" />
    <path d="M5 5l4 4M9 5l-4 4" />
  </svg>
)
