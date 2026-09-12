/**
 * Shared interface primitives.
 *
 * Small, unopinionated building blocks so pages stay readable and every screen
 * handles loading, empty and error states the same way.
 */
import { useEffect } from 'react'
import { AlertIcon, CloseIcon, InboxIcon } from './Icons'

export function Card({ children, className = '', padded = true, ...rest }) {
  return (
    <div className={`mc-panel ${padded ? 'p-5' : ''} ${className}`} {...rest}>
      {children}
    </div>
  )
}

export function Spinner({ size = 18 }) {
  return (
    <span
      className="inline-block animate-spin rounded-full align-[-2px]"
      style={{
        width: size,
        height: size,
        border: '2px solid var(--border-default)',
        borderTopColor: 'var(--brand-solid)',
      }}
      role="status"
      aria-label="Loading"
    />
  )
}

export function Loading({ label = 'Loading…' }) {
  return (
    <div className="flex items-center gap-3 py-10 justify-center" style={{ color: 'var(--text-muted)' }}>
      <Spinner />
      <span className="text-sm">{label}</span>
    </div>
  )
}

export function ErrorMessage({ title = 'Something went wrong', detail, onRetry }) {
  return (
    <div
      className="flex items-start gap-3 rounded-xl p-4 text-sm"
      style={{
        backgroundColor: 'var(--color-rose-100)',
        border: '1px solid var(--color-rose-200)',
        color: 'var(--color-rose-700)',
      }}
      role="alert"
    >
      <AlertIcon size={18} />
      <div className="min-w-0 flex-1">
        <div className="font-semibold">{title}</div>
        {detail && <div className="mt-0.5 break-words opacity-90">{detail}</div>}
      </div>
      {onRetry && (
        <button type="button" className="mc-btn mc-btn-secondary" onClick={onRetry}>
          Retry
        </button>
      )}
    </div>
  )
}

export function EmptyState({ icon, title, description, action }) {
  return (
    <div className="flex flex-col items-center justify-center px-6 py-14 text-center">
      <div
        className="mb-4 flex h-12 w-12 items-center justify-center rounded-full"
        style={{ backgroundColor: 'var(--surface-raised)', color: 'var(--text-faint)' }}
      >
        {icon || <InboxIcon size={22} />}
      </div>
      <h3 className="text-base font-semibold">{title}</h3>
      {description && (
        <p className="mt-1 max-w-sm text-sm" style={{ color: 'var(--text-muted)' }}>
          {description}
        </p>
      )}
      {action && <div className="mt-5">{action}</div>}
    </div>
  )
}

export function Badge({ children, tone = 'neutral' }) {
  const tones = {
    neutral: {},
    brand: { backgroundColor: 'var(--brand-soft)', color: 'var(--brand-soft-text)', borderColor: 'transparent' },
    success: { backgroundColor: 'var(--color-lavender-200)', color: 'var(--color-brand-800)', borderColor: 'transparent' },
    warning: { backgroundColor: 'var(--color-peach-200)', color: 'var(--color-peach-700)', borderColor: 'transparent' },
    danger: { backgroundColor: 'var(--color-rose-200)', color: 'var(--color-rose-700)', borderColor: 'transparent' },
  }
  return (
    <span className="mc-badge" style={tones[tone] || {}}>
      {children}
    </span>
  )
}

export function Field({ label, hint, error, children, htmlFor }) {
  return (
    <div className="mb-4">
      {label && (
        <label className="mc-label" htmlFor={htmlFor}>
          {label}
        </label>
      )}
      {children}
      {hint && !error && (
        <p className="mt-1 text-xs" style={{ color: 'var(--text-faint)' }}>
          {hint}
        </p>
      )}
      {error && (
        <p className="mt-1 text-xs" style={{ color: 'var(--color-rose-700)' }}>
          {error}
        </p>
      )}
    </div>
  )
}

export function Modal({ open, onClose, title, children, footer, width = '32rem' }) {
  useEffect(() => {
    if (!open) return undefined
    function onKey(event) {
      if (event.key === 'Escape') onClose?.()
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [open, onClose])

  if (!open) return null

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      style={{ backgroundColor: 'rgba(18, 21, 36, 0.55)' }}
      onMouseDown={onClose}
      role="dialog"
      aria-modal="true"
      aria-label={typeof title === 'string' ? title : undefined}
    >
      <div
        className="mc-panel w-full max-h-[90vh] overflow-y-auto mc-scroll"
        style={{ maxWidth: width, backgroundColor: 'var(--surface-panel)' }}
        onMouseDown={(event) => event.stopPropagation()}
      >
        <div
          className="flex items-center justify-between px-5 py-4"
          style={{ borderBottom: '1px solid var(--border-subtle)' }}
        >
          <h2 className="text-base font-semibold">{title}</h2>
          <button type="button" className="mc-btn mc-btn-ghost px-2" onClick={onClose} aria-label="Close">
            <CloseIcon size={18} />
          </button>
        </div>
        <div className="p-5">{children}</div>
        {footer && (
          <div
            className="flex justify-end gap-2 px-5 py-4"
            style={{ borderTop: '1px solid var(--border-subtle)' }}
          >
            {footer}
          </div>
        )}
      </div>
    </div>
  )
}

export function StatTile({ label, value, hint, tone = 'brand' }) {
  const accents = {
    brand: 'var(--color-brand-400)',
    lavender: 'var(--color-lavender-400)',
    peach: 'var(--color-peach-500)',
    rose: 'var(--color-rose-500)',
  }
  return (
    <Card className="relative overflow-hidden">
      <span
        className="absolute inset-y-0 left-0 w-1"
        style={{ backgroundColor: accents[tone] || accents.brand }}
        aria-hidden="true"
      />
      <div className="text-xs font-semibold uppercase tracking-wide" style={{ color: 'var(--text-faint)' }}>
        {label}
      </div>
      <div className="mt-1.5 text-2xl font-semibold" style={{ color: 'var(--text-strong)' }}>
        {value}
      </div>
      {hint && (
        <div className="mt-1 text-xs" style={{ color: 'var(--text-muted)' }}>
          {hint}
        </div>
      )}
    </Card>
  )
}
