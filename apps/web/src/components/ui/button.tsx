import clsx from 'clsx';
import Link from 'next/link';
import type { ButtonHTMLAttributes, ReactNode } from 'react';

const base =
  'inline-flex items-center justify-center gap-1.5 rounded font-medium transition-colors ' +
  'disabled:cursor-not-allowed disabled:opacity-50 focus-visible:outline-none';

const variants = {
  primary: 'bg-accent text-white hover:bg-accent/90 active:bg-accent/95',
  secondary: 'border border-line-strong bg-surface text-ink hover:bg-raised',
  ghost: 'text-ink-muted hover:bg-raised hover:text-ink',
  danger: 'border border-high/40 bg-high/10 text-high hover:bg-high/20',
} as const;

const sizes = {
  sm: 'h-7 px-2.5 text-xs',
  md: 'h-8 px-3 text-xs',
  lg: 'h-9 px-4 text-sm',
} as const;

export type ButtonVariant = keyof typeof variants;
export type ButtonSize = keyof typeof sizes;

export function Button({
  variant = 'secondary',
  size = 'md',
  className,
  children,
  loading,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: ButtonVariant;
  size?: ButtonSize;
  loading?: boolean;
}) {
  return (
    <button
      className={clsx(base, variants[variant], sizes[size], className)}
      disabled={props.disabled || loading}
      {...props}
    >
      {loading ? <Spinner /> : null}
      {children}
    </button>
  );
}

export function LinkButton({
  href,
  variant = 'secondary',
  size = 'md',
  className,
  children,
}: {
  href: string;
  variant?: ButtonVariant;
  size?: ButtonSize;
  className?: string;
  children: ReactNode;
}) {
  return (
    <Link href={href} className={clsx(base, variants[variant], sizes[size], className)}>
      {children}
    </Link>
  );
}

export function Spinner({ className }: { className?: string }) {
  return (
    <svg
      className={clsx('h-3.5 w-3.5 animate-spin', className)}
      viewBox="0 0 24 24"
      fill="none"
      aria-hidden
    >
      <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="3" opacity="0.25" />
      <path
        d="M21 12a9 9 0 0 0-9-9"
        stroke="currentColor"
        strokeWidth="3"
        strokeLinecap="round"
      />
    </svg>
  );
}
