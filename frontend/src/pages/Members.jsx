import { useEffect, useState } from 'react'
import { Page, PageHeader } from '../components/AppShell'
import { MembersIcon } from '../components/Icons'
import { Badge, Card, EmptyState, ErrorMessage, Field, Loading, Modal, Spinner } from '../components/ui'
import { addMember, getWorkspace, listMembers, removeMember, resetMemberPassword } from '../api'

export default function Members() {
  const [members, setMembers] = useState(null)
  const [workspace, setWorkspace] = useState(null)
  const [error, setError] = useState(null)
  const [inviteOpen, setInviteOpen] = useState(false)
  const [resetting, setResetting] = useState(null)
  const [newPassword, setNewPassword] = useState('')
  const [form, setForm] = useState({ name: '', email: '', password: '' })
  const [busy, setBusy] = useState(false)

  async function load() {
    try {
      const [memberList, workspaceData] = await Promise.all([
        listMembers(),
        getWorkspace().catch(() => null),
      ])
      setMembers(memberList.members || memberList || [])
      setWorkspace(workspaceData)
    } catch (err) {
      setError(err.message)
    }
  }

  useEffect(() => {
    load()
  }, [])

  async function invite(event) {
    event.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await addMember({ ...form, join_code: workspace?.join_code })
      setForm({ name: '', email: '', password: '' })
      setInviteOpen(false)
      await load()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  async function handleRemove(member) {
    if (!window.confirm(`Remove ${member.name || member.email} from this workspace?`)) return
    await removeMember(member.id).catch((err) => setError(err.message))
    await load()
  }

  async function handleResetPassword(event) {
    event.preventDefault()
    setBusy(true)
    try {
      await resetMemberPassword(resetting.id, newPassword)
      setResetting(null)
      setNewPassword('')
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  if (members === null && !error) return <Page><Loading /></Page>

  return (
    <Page>
      <PageHeader
        title="Members"
        description="People who share this workspace's meetings, notes and memory."
        actions={
          <button type="button" className="mc-btn mc-btn-primary" onClick={() => setInviteOpen(true)}>
            Add member
          </button>
        }
      />

      {error && <div className="mb-4"><ErrorMessage title="Something went wrong" detail={error} /></div>}

      {workspace?.join_code && (
        <Card className="mb-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h2 className="text-sm font-semibold">{workspace.name || 'Workspace'}</h2>
              <p className="mt-0.5 text-sm" style={{ color: 'var(--text-muted)' }}>
                Share this join code so a teammate can create their own account here.
              </p>
            </div>
            <code
              className="rounded-lg px-3 py-1.5 text-sm font-semibold"
              style={{ backgroundColor: 'var(--surface-raised)', color: 'var(--text-strong)' }}
            >
              {workspace.join_code}
            </code>
          </div>
        </Card>
      )}

      <Card padded={false}>
        {(members || []).length === 0 ? (
          <EmptyState icon={<MembersIcon size={22} />} title="No members yet" />
        ) : (
          <ul className="divide-y" style={{ borderColor: 'var(--border-subtle)' }}>
            {members.map((member) => (
              <li key={member.id} className="flex flex-wrap items-center justify-between gap-3 px-5 py-3">
                <div className="min-w-0">
                  <div className="truncate text-sm font-medium" style={{ color: 'var(--text-strong)' }}>
                    {member.name || member.email}
                  </div>
                  <div className="truncate text-xs" style={{ color: 'var(--text-faint)' }}>
                    {member.email}
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  {member.role && <Badge tone={member.role === 'owner' ? 'brand' : 'neutral'}>{member.role}</Badge>}
                  <button
                    type="button"
                    className="mc-btn mc-btn-secondary"
                    onClick={() => setResetting(member)}
                  >
                    Reset password
                  </button>
                  <button type="button" className="mc-btn mc-btn-danger" onClick={() => handleRemove(member)}>
                    Remove
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </Card>

      <Modal open={inviteOpen} onClose={() => setInviteOpen(false)} title="Add a member">
        <form onSubmit={invite}>
          <Field label="Name" htmlFor="member-name">
            <input
              id="member-name"
              className="mc-input"
              value={form.name}
              onChange={(event) => setForm({ ...form, name: event.target.value })}
            />
          </Field>
          <Field label="Email" htmlFor="member-email">
            <input
              id="member-email"
              type="email"
              required
              className="mc-input"
              value={form.email}
              onChange={(event) => setForm({ ...form, email: event.target.value })}
            />
          </Field>
          <Field label="Temporary password" htmlFor="member-password">
            <input
              id="member-password"
              type="password"
              required
              className="mc-input"
              value={form.password}
              onChange={(event) => setForm({ ...form, password: event.target.value })}
            />
          </Field>
          <button type="submit" className="mc-btn mc-btn-primary w-full" disabled={busy}>
            {busy ? <Spinner size={14} /> : null} Add member
          </button>
        </form>
      </Modal>

      <Modal
        open={Boolean(resetting)}
        onClose={() => setResetting(null)}
        title={`Reset password for ${resetting?.name || resetting?.email || ''}`}
      >
        <form onSubmit={handleResetPassword}>
          <Field label="New password" htmlFor="new-password">
            <input
              id="new-password"
              type="password"
              required
              className="mc-input"
              value={newPassword}
              onChange={(event) => setNewPassword(event.target.value)}
            />
          </Field>
          <button type="submit" className="mc-btn mc-btn-primary w-full" disabled={busy}>
            {busy ? <Spinner size={14} /> : null} Set password
          </button>
        </form>
      </Modal>
    </Page>
  )
}
