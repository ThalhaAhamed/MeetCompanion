import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../api', () => ({
  addMember: vi.fn(),
  getWorkspace: vi.fn(),
  listMembers: vi.fn(),
  removeMember: vi.fn(),
  resetMemberPassword: vi.fn(),
  setMemberRole: vi.fn(),
  setWorkspacePermissions: vi.fn(),
}))
import { getWorkspace, listMembers, setWorkspacePermissions } from '../api'
import Members from '../pages/Members'
import { UserContext } from '../user'

const permissions = [
  { key: 'create_content', label: 'Add content', description: 'd', default: true },
  { key: 'delete_content', label: 'Delete content', description: 'd', default: false },
]
const members = { members: [
  { id: 'u-owner', name: 'Owner', email: 'owner@x.test', role: 'owner' },
  { id: 'u-member', name: 'Member', email: 'member@x.test', role: 'member' },
] }

function renderAs(user) {
  return render(
    <UserContext.Provider value={user}>
      <Members />
    </UserContext.Provider>,
  )
}

describe('Members page permissions', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    listMembers.mockResolvedValue(members)
  })

  it('lets an owner see the join code, the panel, and flip a permission that saves', async () => {
    getWorkspace.mockResolvedValue({
      name: 'Acme', join_code: 'abc123', permissions,
      member_permissions: { create_content: true, delete_content: false },
    })
    setWorkspacePermissions.mockResolvedValue({ member_permissions: { create_content: true, delete_content: true } })
    renderAs({ id: 'u-owner', role: 'owner', permissions: { invite_members: true } })

    expect(await screen.findByText('abc123')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Add member' })).toBeInTheDocument()
    const del = await screen.findByRole('switch', { name: 'Delete content' })
    expect(del).toHaveAttribute('aria-checked', 'false')
    expect(screen.getByRole('switch', { name: 'Add content' })).toHaveAttribute('aria-checked', 'true')

    fireEvent.click(del)
    await waitFor(() => expect(setWorkspacePermissions).toHaveBeenCalledWith({ delete_content: true }))
    await waitFor(() => expect(screen.getByRole('switch', { name: 'Delete content' })).toHaveAttribute('aria-checked', 'true'))
  })

  it('shows a member neither the panel, the join code, nor Add member - only Leave on themselves', async () => {
    getWorkspace.mockResolvedValue({ name: 'Acme', join_code: null, permissions, member_permissions: { create_content: true, delete_content: false } })
    renderAs({ id: 'u-member', role: 'member', permissions: { invite_members: false } })

    await screen.findByText('member@x.test')
    expect(screen.queryByRole('switch')).toBeNull()
    expect(screen.queryByText('What members can do')).toBeNull()
    expect(screen.queryByRole('button', { name: 'Add member' })).toBeNull()
    expect(screen.queryByRole('button', { name: /Make owner|Make member|Reset password|^Remove$/ })).toBeNull()
    const me = screen.getByText('member@x.test').closest('li')
    expect(within(me).getByRole('button', { name: 'Leave' })).toBeInTheDocument()
  })
})
