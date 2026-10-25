function Icon({ size = 20, children, ...props }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
      {...props}
    >
      {children}
    </svg>
  )
}

export function LogoIcon({ size = 18 }) {
  return (
    <Icon size={size} strokeWidth="1.7">
      <path d="M4.5 19.5v-9L12 4.5l7.5 6v9" />
      <path d="M9.5 19.5v-5.2h5v5.2" />
      <path d="M9.2 10.6h.01M14.8 10.6h.01" strokeWidth="2.4" />
    </Icon>
  )
}

export function ImageIcon({ size = 20 }) {
  return (
    <Icon size={size}>
      <rect x="3" y="4.5" width="18" height="15" rx="2.5" />
      <circle cx="8.5" cy="9.5" r="1.4" />
      <path d="m3.8 17 4.7-4.7 4 4 3-3 4.7 4.7" />
    </Icon>
  )
}

export function XIcon({ size = 18 }) {
  return (
    <Icon size={size}>
      <path d="M6 6l12 12M18 6 6 18" />
    </Icon>
  )
}

export function CheckIcon({ size = 20 }) {
  return (
    <Icon size={size}>
      <path d="m5 12.5 4.3 4.3L19 7" />
    </Icon>
  )
}

export function AlertIcon({ size = 18 }) {
  return (
    <Icon size={size}>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 7.8v4.9" />
      <path d="M12 16.2h.01" strokeWidth="2.2" />
    </Icon>
  )
}
