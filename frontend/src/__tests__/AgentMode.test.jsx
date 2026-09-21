import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter } from 'react-router-dom'

vi.mock('../api', () => ({
  activateAgent: vi.fn(),
  createAgent: vi.fn(),
  deleteAgent: vi.fn(),
  setAgentMode: vi.fn(),
  getAgent: vi.fn(),
  getAgentCredentials: vi.fn(),
  getAgentTemplate: vi.fn(),
  listAgents: vi.fn(),
  listImportableAgents: vi.fn(),
  updateAgent: vi.fn(),
  updateAgentTemplate: vi.fn(),
  setMeetstreamApiKey: vi.fn(),
}))
import { getAgent, getAgentCredentials, getAgentTemplate, listAgents, setAgentMode } from '../api'
import Agent from '../pages/Agent'
import { UserContext } from '../user'

const config = { AgentConfigID: 'ag-1', AgentName: 'Ada', Mode: 'realtime', InteractionMode: 'voice', Model: { provider: 'openai', model: 'gpt-4.1' } }

function renderAs(user) {
  return render(
    <MemoryRouter>
      <UserContext.Provider value={user}>
        <Agent />
      </UserContext.Provider>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  listAgents.mockResolvedValue({ agent_configs: [{ ...config, IsActive: true }] })
  getAgent.mockResolvedValue(config)
  getAgentCredentials.mockResolvedValue(null)
  getAgentTemplate.mockResolvedValue({ provider: 'openai' })
})

describe('how the agent takes part in a call', () => {
  it('shows the three modes, voice selected, and saves a change', async () => {
    setAgentMode.mockResolvedValue({ agent_config_id: 'ag-1', mode: 'chat' })
    renderAs({ id: 'u1', role: 'owner', permissions: { manage_agents: true } })
    const voice = await screen.findByRole('radio', { name: /^Voice Joins/ })
    expect(voice).toHaveAttribute('aria-checked', 'true')
    expect(screen.queryByText(/start a message with/)).toBeNull()

    fireEvent.click(screen.getByRole('radio', { name: /^Chat Stays/ }))
    await waitFor(() => expect(setAgentMode).toHaveBeenCalledWith('ag-1', 'chat'))
    await waitFor(() => expect(screen.getByRole('radio', { name: /^Chat Stays/ })).toHaveAttribute('aria-checked', 'true'))
    // How to ask, with the agent's own name.
    expect(screen.getByText(/start a message with/)).toBeInTheDocument()
    expect(screen.getByText('@Ada')).toBeInTheDocument()
  })

  it('a member without manage_agents can see the mode but not change it', async () => {
    renderAs({ id: 'u2', role: 'member', permissions: { manage_agents: false } })
    const voice = await screen.findByRole('radio', { name: /^Voice Joins/ })
    expect(voice).toBeDisabled()
    fireEvent.click(screen.getByRole('radio', { name: /Voice and chat/ }))
    expect(setAgentMode).not.toHaveBeenCalled()
  })
})
