import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { Page, PageHeader } from '../components/AppShell'
import { SearchIcon } from '../components/Icons'
import { Badge, Card, EmptyState, ErrorMessage, Spinner } from '../components/ui'
import { getKnowledgeGraph } from '../api'

/**
 * Knowledge graph.
 *
 * A dependency-free force simulation: pairwise repulsion, spring edges, and
 * explicit collision separation so hub nodes do not overlap. Kept hand-written
 * rather than pulling in a graph library, which would be a large dependency
 * for one screen.
 */

const NODE_COLOURS = {
  meeting: 'var(--color-brand-500)',
  person: 'var(--color-lavender-400)',
  memory: 'var(--color-peach-500)',
  action_item: 'var(--color-rose-500)',
  project: 'var(--color-brand-700)',
  customer: 'var(--color-brand-300)',
}

const BASE_RADIUS = { meeting: 15, person: 11, customer: 11, project: 11, memory: 7, action_item: 7 }

/** Children sit close to their meeting; looser links keep clusters apart. */
const EDGE_DISTANCE = {
  produced: 55,
  said: 45,
  owns: 45,
  participated_in: 100,
  for_customer: 110,
  for_project: 110,
}

const WIDTH = 1000
const HEIGHT = 580
const SETTLE_SPEED = 0.12
const MAX_RUNTIME_MS = 6000

function radiusFor(type, degree) {
  return (BASE_RADIUS[type] || 7) + Math.min(Math.sqrt(degree) * 3, 14)
}

function useForceLayout(nodes, edges) {
  const positions = useRef(new Map())
  const draggingId = useRef(null)
  const settledRef = useRef(false)
  const [, setTick] = useState(0)
  const [settled, setSettled] = useState(false)

  useEffect(() => {
    settledRef.current = false
    setSettled(false)

    const pos = positions.current
    for (const node of nodes) {
      if (!pos.has(node.id)) {
        pos.set(node.id, {
          x: WIDTH / 2 + (Math.random() - 0.5) * 320,
          y: HEIGHT / 2 + (Math.random() - 0.5) * 320,
          vx: 0,
          vy: 0,
        })
      }
    }
    for (const id of [...pos.keys()]) {
      if (!nodes.some((node) => node.id === id)) pos.delete(id)
    }

    const degree = new Map(nodes.map((node) => [node.id, 0]))
    for (const edge of edges) {
      degree.set(edge.source, (degree.get(edge.source) || 0) + 1)
      degree.set(edge.target, (degree.get(edge.target) || 0) + 1)
    }
    const radius = new Map(nodes.map((n) => [n.id, radiusFor(n.type, degree.get(n.id) || 0)]))
    const ids = nodes.map((node) => node.id)
    const deadline = performance.now() + MAX_RUNTIME_MS

    let frame = 0
    function step() {
      for (let i = 0; i < ids.length; i++) {
        const a = pos.get(ids[i])
        const ra = radius.get(ids[i])
        for (let j = i + 1; j < ids.length; j++) {
          const b = pos.get(ids[j])
          const dx = a.x - b.x
          const dy = a.y - b.y
          const distSq = Math.max(dx * dx + dy * dy, 1)
          const dist = Math.sqrt(distSq)

          let fx = (dx / dist) * (3200 / distSq)
          let fy = (dy / dist) * (3200 / distSq)

          // Without explicit separation, dense clusters render as blobs no
          // matter how the rest of the layout settles.
          const minDist = ra + radius.get(ids[j]) + 6
          if (dist < minDist) {
            const push = (minDist - dist) * 0.5
            fx += (dx / dist) * push
            fy += (dy / dist) * push
          }
          a.vx += fx; a.vy += fy
          b.vx -= fx; b.vy -= fy
        }
      }

      for (const edge of edges) {
        const a = pos.get(edge.source)
        const b = pos.get(edge.target)
        if (!a || !b) continue
        const dx = b.x - a.x
        const dy = b.y - a.y
        const dist = Math.max(Math.sqrt(dx * dx + dy * dy), 1)
        const force = (dist - (EDGE_DISTANCE[edge.type] || 90)) * 0.03
        const fx = (dx / dist) * force
        const fy = (dy / dist) * force
        a.vx += fx; a.vy += fy
        b.vx -= fx; b.vy -= fy
      }

      // Gravity eases off as the graph grows, or it fights the repulsion that
      // separates clusters.
      const gravity = 0.001 / Math.max(1, Math.sqrt(ids.length / 20))
      let totalSpeed = 0
      for (const id of ids) {
        if (id === draggingId.current) continue
        const p = pos.get(id)
        p.vx = (p.vx + (WIDTH / 2 - p.x) * gravity) * 0.82
        p.vy = (p.vy + (HEIGHT / 2 - p.y) * gravity) * 0.82
        p.x = Math.max(24, Math.min(WIDTH - 24, p.x + p.vx))
        p.y = Math.max(24, Math.min(HEIGHT - 24, p.y + p.vy))
        totalSpeed += Math.abs(p.vx) + Math.abs(p.vy)
      }

      setTick((t) => t + 1)

      const calm = ids.length > 0 && totalSpeed / ids.length < SETTLE_SPEED
      if (calm || performance.now() > deadline) {
        if (!settledRef.current) {
          settledRef.current = true
          setSettled(true)
        }
        // Keep running a little after settling so a drag stays responsive.
        if (performance.now() > deadline) return
      }
      frame = requestAnimationFrame(step)
    }

    frame = requestAnimationFrame(step)
    return () => cancelAnimationFrame(frame)
  }, [nodes, edges])

  return {
    positions: positions.current,
    draggingId,
    settled,
    bump: () => setTick((t) => t + 1),
  }
}

function NodeDetail({ node, nodes, edges }) {
  const byId = useMemo(() => new Map(nodes.map((n) => [n.id, n])), [nodes])
  const related = useMemo(() => {
    if (!node) return []
    const out = []
    for (const edge of edges) {
      if (edge.source === node.id) out.push(byId.get(edge.target))
      else if (edge.target === node.id) out.push(byId.get(edge.source))
    }
    return out.filter(Boolean)
  }, [node, edges, byId])

  if (!node) {
    return (
      <EmptyState
        title="Select a node"
        description="Click anything in the graph to see what it connects to."
      />
    )
  }

  return (
    <div className="p-5">
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <Badge tone="brand">{node.type.replace('_', ' ')}</Badge>
        {node.date && (
          <span className="text-xs" style={{ color: 'var(--text-faint)' }}>
            {new Date(node.date).toLocaleDateString()}
          </span>
        )}
      </div>

      <h3 className="text-base font-semibold">{node.label}</h3>

      {node.summary && (
        <p className="mt-2 text-sm leading-relaxed" style={{ color: 'var(--text-muted)' }}>
          {node.summary.slice(0, 320)}
        </p>
      )}
      {node.content && (
        <p className="mt-2 text-sm leading-relaxed" style={{ color: 'var(--text-muted)' }}>
          {node.content}
        </p>
      )}
      {node.task && <p className="mt-2 text-sm">{node.task}</p>}

      <div className="mt-3 flex flex-wrap gap-1.5">
        {node.speaker && <Badge>{node.speaker}</Badge>}
        {node.owner && <Badge>{node.owner}</Badge>}
        {node.status && <Badge>{node.status}</Badge>}
        {node.platform && <Badge>{node.platform}</Badge>}
      </div>

      {node.meeting_id && (
        <Link
          to={`/meetings/${node.meeting_id}`}
          className="mc-btn mc-btn-secondary mt-4 w-full"
        >
          Open meeting
        </Link>
      )}

      <div className="mt-5">
        <div
          className="mb-2 text-[0.65rem] font-semibold uppercase tracking-[0.14em]"
          style={{ color: 'var(--text-faint)' }}
        >
          Connected ({related.length})
        </div>
        <ul className="mc-scroll max-h-56 space-y-1 overflow-y-auto">
          {related.slice(0, 40).map((item) => (
            <li
              key={item.id}
              className="truncate rounded-lg px-2 py-1.5 text-xs"
              style={{ backgroundColor: 'var(--surface-raised)', color: 'var(--text-default)' }}
            >
              <span
                className="mr-2 inline-block h-2 w-2 rounded-full align-middle"
                style={{ backgroundColor: NODE_COLOURS[item.type] || 'var(--text-faint)' }}
              />
              {item.label}
            </li>
          ))}
        </ul>
      </div>
    </div>
  )
}

export default function Graph() {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [typeFilter, setTypeFilter] = useState('all')
  const [query, setQuery] = useState('')
  const [selectedId, setSelectedId] = useState(null)
  const [view, setView] = useState({ x: 0, y: 0, k: 1 })

  const svgRef = useRef(null)
  const panRef = useRef(null)
  const dragRef = useRef(null)

  useEffect(() => {
    getKnowledgeGraph()
      .then(setData)
      .catch((err) => setError(err.message))
  }, [])

  const allNodes = data?.nodes || []
  const allEdges = data?.edges || []

  // Memoised on stable inputs: rebuilding these arrays every render restarts
  // the simulation on every animation frame.
  const nodes = useMemo(
    () => (typeFilter === 'all' ? allNodes : allNodes.filter((n) => n.type === typeFilter)),
    [allNodes, typeFilter],
  )
  const edges = useMemo(() => {
    const ids = new Set(nodes.map((n) => n.id))
    return allEdges.filter((e) => ids.has(e.source) && ids.has(e.target))
  }, [allEdges, nodes])

  const degrees = useMemo(() => {
    const counts = new Map(nodes.map((n) => [n.id, 0]))
    for (const edge of edges) {
      counts.set(edge.source, (counts.get(edge.source) || 0) + 1)
      counts.set(edge.target, (counts.get(edge.target) || 0) + 1)
    }
    return counts
  }, [nodes, edges])

  const { positions, draggingId, settled, bump } = useForceLayout(nodes, edges)

  /** Plain substring matching over labels - distinct from semantic search. */
  const matches = useMemo(() => {
    const term = query.trim().toLowerCase()
    if (!term) return null
    const found = new Set()
    for (const node of nodes) {
      const haystack = [node.label, node.content, node.task, node.summary, node.speaker, node.owner]
        .filter(Boolean)
        .join(' ')
        .toLowerCase()
      if (haystack.includes(term)) found.add(node.id)
    }
    return found
  }, [query, nodes])

  const selected = allNodes.find((n) => n.id === selectedId) || null
  const neighbours = useMemo(() => {
    if (!selectedId) return null
    const ids = new Set([selectedId])
    for (const edge of edges) {
      if (edge.source === selectedId) ids.add(edge.target)
      if (edge.target === selectedId) ids.add(edge.source)
    }
    return ids
  }, [selectedId, edges])

  function toGraphSpace(clientX, clientY) {
    const rect = svgRef.current.getBoundingClientRect()
    const x = ((clientX - rect.left) / rect.width) * WIDTH
    const y = ((clientY - rect.top) / rect.height) * HEIGHT
    return { x: (x - view.x) / view.k, y: (y - view.y) / view.k }
  }

  const handleWheel = useCallback(
    (event) => {
      const rect = svgRef.current.getBoundingClientRect()
      const cx = ((event.clientX - rect.left) / rect.width) * WIDTH
      const cy = ((event.clientY - rect.top) / rect.height) * HEIGHT
      const factor = event.deltaY < 0 ? 1.12 : 1 / 1.12
      setView((current) => {
        const k = Math.max(0.3, Math.min(3, current.k * factor))
        return {
          k,
          x: cx - ((cx - current.x) / current.k) * k,
          y: cy - ((cy - current.y) / current.k) * k,
        }
      })
    },
    [view.k],
  )

  // React attaches onWheel passively, so preventDefault() inside it is ignored
  // and the page scrolls while the graph zooms. A native listener is the only
  // way to stop that.
  useEffect(() => {
    const element = svgRef.current
    if (!element) return undefined

    function onWheel(event) {
      event.preventDefault()
      handleWheel(event)
    }
    element.addEventListener('wheel', onWheel, { passive: false })
    return () => element.removeEventListener('wheel', onWheel)
  }, [handleWheel, settled, nodes.length])

  function onNodeMouseDown(event, node) {
    event.stopPropagation()
    const point = toGraphSpace(event.clientX, event.clientY)
    const position = positions.get(node.id)
    dragRef.current = {
      id: node.id,
      moved: false,
      offsetX: point.x - position.x,
      offsetY: point.y - position.y,
    }
    draggingId.current = node.id
  }

  function onMouseMove(event) {
    if (dragRef.current) {
      const point = toGraphSpace(event.clientX, event.clientY)
      const position = positions.get(dragRef.current.id)
      if (position) {
        position.x = point.x - dragRef.current.offsetX
        position.y = point.y - dragRef.current.offsetY
        position.vx = 0
        position.vy = 0
        // The simulation stops driving re-renders once settled, so a drag has
        // to request its own.
        bump()
      }
      dragRef.current.moved = true
      return
    }
    if (panRef.current) {
      const start = panRef.current
      setView({
        ...start.origin,
        x: start.origin.x + (event.clientX - start.startX),
        y: start.origin.y + (event.clientY - start.startY),
      })
    }
  }

  function onMouseUp(event, node) {
    if (dragRef.current) {
      const wasClick = !dragRef.current.moved
      draggingId.current = null
      dragRef.current = null
      if (wasClick && node) setSelectedId((current) => (current === node.id ? null : node.id))
    }
    panRef.current = null
  }

  if (error) {
    return (
      <Page>
        <ErrorMessage title="Could not load the graph" detail={error} onRetry={() => window.location.reload()} />
      </Page>
    )
  }

  return (
    <Page>
      <PageHeader
        title="Knowledge graph"
        description="How your meetings, people, decisions and action items connect."
        actions={
          <>
            <div className="mc-search w-56">
              <SearchIcon size={16} />
              <input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Find a node…"
                aria-label="Find a node in the graph"
              />
            </div>
            <select
              className="mc-input w-auto"
              value={typeFilter}
              onChange={(event) => setTypeFilter(event.target.value)}
              aria-label="Filter by node type"
            >
              <option value="all">All types</option>
              <option value="meeting">Meetings</option>
              <option value="person">People</option>
              <option value="memory">Memories</option>
              <option value="action_item">Action items</option>
              <option value="project">Projects</option>
              <option value="customer">Customers</option>
            </select>
          </>
        }
      />

      <div className="grid gap-5 lg:grid-cols-[1fr_20rem] items-start">
        <Card padded={false} className="overflow-hidden">
          {data === null ? (
            <div className="flex h-[520px] items-center justify-center gap-3" style={{ color: 'var(--text-muted)' }}>
              <Spinner /> <span className="text-sm">Loading graph…</span>
            </div>
          ) : nodes.length === 0 ? (
            <EmptyState
              title="Nothing to show"
              description="Meetings need participants, memories or action items before they appear here."
            />
          ) : !settled ? (
            <div className="flex h-[520px] flex-col items-center justify-center gap-3" style={{ color: 'var(--text-muted)' }}>
              <Spinner size={26} />
              <span className="text-sm">Arranging graph…</span>
            </div>
          ) : (
            <svg
              ref={svgRef}
              viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
              className="block w-full touch-none select-none"
              style={{ backgroundColor: 'var(--surface-sunken)', cursor: 'grab' }}
              onMouseDown={(event) => {
                panRef.current = { startX: event.clientX, startY: event.clientY, origin: { ...view } }
              }}
              onMouseMove={onMouseMove}
              onMouseUp={() => onMouseUp()}
              onMouseLeave={() => onMouseUp()}
            >
              <g transform={`translate(${view.x},${view.y}) scale(${view.k})`}>
                {edges.map((edge, index) => {
                  const a = positions.get(edge.source)
                  const b = positions.get(edge.target)
                  if (!a || !b) return null
                  const dimmed =
                    (neighbours && !(neighbours.has(edge.source) && neighbours.has(edge.target))) ||
                    (matches && !(matches.has(edge.source) && matches.has(edge.target)))
                  return (
                    <line
                      key={index}
                      x1={a.x} y1={a.y} x2={b.x} y2={b.y}
                      stroke="var(--border-strong)"
                      strokeWidth={1}
                      opacity={dimmed ? 0.08 : 0.5}
                    />
                  )
                })}

                {nodes.map((node) => {
                  const position = positions.get(node.id)
                  if (!position) return null
                  const dimmed =
                    (neighbours && !neighbours.has(node.id)) || (matches && !matches.has(node.id))
                  const isMatch = matches?.has(node.id)
                  const r = radiusFor(node.type, degrees.get(node.id) || 0)
                  const showLabel = view.k > 0.75 || selectedId === node.id || isMatch

                  return (
                    <g
                      key={node.id}
                      opacity={dimmed ? 0.12 : 1}
                      style={{ cursor: 'pointer' }}
                      onMouseDown={(event) => onNodeMouseDown(event, node)}
                      onMouseUp={(event) => { event.stopPropagation(); onMouseUp(event, node) }}
                    >
                      <circle
                        cx={position.x}
                        cy={position.y}
                        r={r}
                        fill={NODE_COLOURS[node.type] || 'var(--text-faint)'}
                        stroke={selectedId === node.id || isMatch ? 'var(--text-strong)' : 'transparent'}
                        strokeWidth={2}
                      />
                      {showLabel && (
                        <text
                          x={position.x}
                          y={position.y + r + 11}
                          textAnchor="middle"
                          fontSize="9"
                          fill="var(--text-muted)"
                        >
                          {node.label.length > 26 ? `${node.label.slice(0, 26)}…` : node.label}
                        </text>
                      )}
                    </g>
                  )
                })}
              </g>
            </svg>
          )}

          <div
            className="flex flex-wrap items-center gap-3 px-5 py-3 text-xs"
            style={{ borderTop: '1px solid var(--border-subtle)', color: 'var(--text-muted)' }}
          >
            {Object.entries(NODE_COLOURS).map(([type, colour]) => (
              <span key={type} className="flex items-center gap-1.5">
                <span className="inline-block h-2.5 w-2.5 rounded-full" style={{ backgroundColor: colour }} />
                {type.replace('_', ' ')}
              </span>
            ))}
            <span className="ml-auto" style={{ color: 'var(--text-faint)' }}>
              {nodes.length} nodes · {edges.length} links · scroll to zoom, drag to move
            </span>
          </div>
        </Card>

        <Card padded={false} className="lg:sticky lg:top-24">
          <NodeDetail node={selected} nodes={allNodes} edges={allEdges} />
        </Card>
      </div>
    </Page>
  )
}
