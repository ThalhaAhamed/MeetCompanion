import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../api', () => ({
  listMyWorkspaces: vi.fn(),
  listConnections: vi.fn(),
  activateWorkspace: vi.fn(),
  activateConnection: vi.fn(),
  createWorkspace: vi.fn(),
  addConnection: vi.fn(),
  joinWorkspace: vi.fn(),
}))
import { activateConnection, addConnection, activateWorkspace, joinWorkspace, listConnections, listMyWorkspaces } from '../api'
import AppShell from '../components/AppShell'

function renderShell() {
  return render(
    <MemoryRouter>
      <AppShell user={{ name: 'Alex', email: 'alex@x.test' }} onSignOut={() => {}}>
        <div />
      </AppShell>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  // Reload is called after a switch; stub it so jsdom does not complain.
  Object.defineProperty(window, 'location', { value: { reload: vi.fn(), pathname: '/' }, writable: true })
})

describe('workspace switcher across databases', () => {
  it('single database: a flat list, activateWorkspace on click', async () => {
    listMyWorkspaces.mockResolvedValue({ workspaces: [
      { id: 'w1', name: 'Mine', role: 'owner', is_active: true },
      { id: 'w2', name: 'Second', role: 'owner', is_active: false },
    ] })
    listConnections.mockRejectedValue(new Error('404'))  // not the desktop app
    renderShell()
    fireEvent.click(await screen.findByTitle('Switch workspace'))
    fireEvent.click(await screen.findByRole('menuitemradio', { name: /Second/ }))
    await waitFor(() => expect(activateWorkspace).toHaveBeenCalledWith('w2'))
    expect(activateConnection).not.toHaveBeenCalled()
  })

  it('two databases: workspaces grouped by connection, foreign switch goes through activateConnection', async () => {
    listMyWorkspaces.mockResolvedValue({ workspaces: [{ id: 'w1', name: 'Mine', role: 'owner', is_active: true }] })
    listConnections.mockResolvedValue({ connections: [
      { id: 'c1', label: 'Local SQLite · me.db', active: true, reachable: true, signed_in: true,
        workspaces: [{ id: 'w1', name: 'Mine', role: 'owner', is_active: true }] },
      { id: 'c2', label: 'Railway · team', active: false, reachable: true, signed_in: true,
        workspaces: [{ id: 'w9', name: 'Team Co', role: 'member', is_active: true }] },
    ] })
    renderShell()
    fireEvent.click(await screen.findByTitle('Switch workspace'))

    // Both databases labelled, both workspaces shown.
    expect(await screen.findByText('Local SQLite · me.db')).toBeInTheDocument()
    expect(screen.getByText('Railway · team')).toBeInTheDocument()
    expect(screen.getByRole('menuitemradio', { name: /Mine/ })).toHaveAttribute('aria-checked', 'true')

    fireEvent.click(screen.getByRole('menuitemradio', { name: /Team Co/ }))
    await waitFor(() => expect(activateConnection).toHaveBeenCalledWith('c2', 'w9'))
    expect(activateWorkspace).not.toHaveBeenCalled()
  })

  it('a connection with no account here offers sign-in; an unreachable one is disabled', async () => {
    listMyWorkspaces.mockResolvedValue({ workspaces: [{ id: 'w1', name: 'Mine', role: 'owner', is_active: true }] })
    listConnections.mockResolvedValue({ connections: [
      { id: 'c1', label: 'Home', active: true, reachable: true, signed_in: true, workspaces: [{ id: 'w1', name: 'Mine', role: 'owner', is_active: true }] },
      { id: 'c2', label: 'Team', active: false, reachable: true, signed_in: false, workspaces: [] },
      { id: 'c3', label: 'Old laptop', active: false, reachable: false, signed_in: true, workspaces: [] },
    ] })
    renderShell()
    fireEvent.click(await screen.findByTitle('Switch workspace'))
    const signIn = await screen.findByRole('button', { name: /Sign in on this database/ })
    fireEvent.click(signIn)
    await waitFor(() => expect(activateConnection).toHaveBeenCalledWith('c2', null))
    expect(screen.getByRole('button', { name: /Unreachable/ })).toBeDisabled()
  })
})

describe('joining a workspace from the picker', () => {
  const oneDb = {
    connections: [{ id: 'c1', label: 'Home', active: true, reachable: true, signed_in: true,
      workspaces: [{ id: 'w1', name: 'Mine', role: 'owner', is_active: true }] }],
  }

  beforeEach(() => {
    listMyWorkspaces.mockResolvedValue({ workspaces: [{ id: 'w1', name: 'Mine', role: 'owner', is_active: true }] })
    window.sessionStorage.clear()
  })

  async function openJoinForm() {
    renderShell()
    fireEvent.click(await screen.findByTitle('Switch workspace'))
    fireEvent.click(await screen.findByRole('button', { name: /Join a workspace/ }))
  }

  it('a code alone joins on the database we are already on', async () => {
    listConnections.mockResolvedValue(oneDb)
    await openJoinForm()
    fireEvent.change(await screen.findByLabelText('Workspace join code'), { target: { value: 'abc123' } })
    fireEvent.click(screen.getByRole('button', { name: 'Join' }))
    await waitFor(() => expect(joinWorkspace).toHaveBeenCalledWith('abc123'))
    expect(addConnection).not.toHaveBeenCalled()
  })

  it('a code plus a connection string switches database, then joins when already known there', async () => {
    listConnections.mockResolvedValue(oneDb)
    addConnection.mockResolvedValue({ id: 'c2' })
    activateConnection.mockResolvedValue({ switched: true, signed_in: true })
    await openJoinForm()
    fireEvent.change(await screen.findByLabelText('Workspace join code'), { target: { value: 'abc123' } })
    fireEvent.change(screen.getByLabelText('Database connection string'), { target: { value: 'postgresql://u:p@h/db' } })
    fireEvent.click(screen.getByRole('button', { name: 'Join' }))
    await waitFor(() => expect(addConnection).toHaveBeenCalledWith({ url: 'postgresql://u:p@h/db' }))
    expect(activateConnection).toHaveBeenCalledWith('c2', null)
    await waitFor(() => expect(joinWorkspace).toHaveBeenCalledWith('abc123'))
    expect(window.sessionStorage.getItem('meet-companion:pending-join')).toBeNull()
  })

  it('with no account on that database the code is carried to account creation', async () => {
    listConnections.mockResolvedValue(oneDb)
    addConnection.mockResolvedValue({ id: 'c2' })
    activateConnection.mockResolvedValue({ switched: true, signed_in: false })
    await openJoinForm()
    fireEvent.change(await screen.findByLabelText('Workspace join code'), { target: { value: 'abc123' } })
    fireEvent.change(screen.getByLabelText('Database connection string'), { target: { value: 'postgresql://u:p@h/db' } })
    fireEvent.click(screen.getByRole('button', { name: 'Join' }))
    await waitFor(() => expect(window.sessionStorage.getItem('meet-companion:pending-join')).toBe('abc123'))
    expect(joinWorkspace).not.toHaveBeenCalled()  // no account there to add a membership to
  })

  it('a failed join surfaces the message instead of reloading', async () => {
    listConnections.mockResolvedValue(oneDb)
    joinWorkspace.mockRejectedValue(new Error('No workspace found with that join code.'))
    await openJoinForm()
    fireEvent.change(await screen.findByLabelText('Workspace join code'), { target: { value: 'nope' } })
    fireEvent.click(screen.getByRole('button', { name: 'Join' }))
    expect(await screen.findByText(/No workspace found with that join code/)).toBeInTheDocument()
    expect(window.location.reload).not.toHaveBeenCalled()
  })
})
