import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../api', () => ({ addMember: vi.fn(), login: vi.fn() }))
import { addMember, login } from '../api'
import SignIn from '../pages/SignIn'

/** Both the mode tabs and the submit button carry these names; we want the submit. */
function submitButton(name) {
  return screen.getAllByRole('button', { name }).find((b) => b.getAttribute('type') === 'submit')
}

const KEY = 'meet-companion:pending-join'

beforeEach(() => {
  vi.clearAllMocks()
  window.sessionStorage.clear()
  addMember.mockResolvedValue({ id: 'u1', role: 'member' })
  login.mockResolvedValue({ authenticated: true })
})

describe('sign-in', () => {
  it('opens on sign-in for an install that already has accounts', () => {
    render(<SignIn onSignedIn={vi.fn()} hasMembers />)
    expect(submitButton('Sign in')).toBeTruthy()
    expect(screen.queryByLabelText('Your name')).toBeNull()
  })

  it('a join code carried from the picker opens account creation with it filled in', async () => {
    window.sessionStorage.setItem(KEY, 'abc123')
    const onSignedIn = vi.fn()
    render(<SignIn onSignedIn={onSignedIn} hasMembers />)

    expect(await screen.findByText(/Connected to that database/)).toBeInTheDocument()
    expect(screen.getByLabelText('Your name')).toBeInTheDocument()
    const code = screen.getByLabelText(/Join code/i)
    expect(code).toHaveValue('abc123')
    // Taken once: a reload must not resurrect it.
    expect(window.sessionStorage.getItem(KEY)).toBeNull()

    fireEvent.change(screen.getByLabelText('Your name'), { target: { value: 'Ada' } })
    fireEvent.change(screen.getByLabelText('Email'), { target: { value: 'ada@x.test' } })
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'correct-horse-battery' } })
    fireEvent.click(submitButton('Create account'))

    await waitFor(() => expect(addMember).toHaveBeenCalledWith(expect.objectContaining({
      email: 'ada@x.test', join_code: 'abc123',
    })))
    await waitFor(() => expect(onSignedIn).toHaveBeenCalled())
  })
})
