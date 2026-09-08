import { useEffect, useMemo, useRef, useState } from 'react'
import { getKnowledgeGraph, searchMemory } from './api'

const COLORS = {
  meeting: '#ff8a3d',
  person: '#7fb2ff',
  customer: '#8fd6a8',
  project: '#e69be6',
  memory: '#ffd166',
  action_item: '#f28ba0',
}
const BASE_RADIUS = {
  meeting: 16,
  person: 12,
  customer: 12,
  project: 12,
  memory: 8,
  action_item: 8,
}

function computeDegrees(nodes, edges) {
  const degree = new Map(nodes.map((n) => [n.id, 0]))
  for (const e of edges) {
    if (degree.has(e.source)) degree.set(e.source, degree.get(e.source) + 1)
    if (degree.has(e.target)) degree.set(e.target, degree.get(e.target) + 1)
  }
  return degree
}

// Minimal dependency-free force simulation - repulsion between all nodes,
// spring attraction along edges, gentle pull toward center. Settles after a
// few seconds like Obsidian's graph does, but a drag can always move a node
// (via bump()) even once the simulation itself has gone idle.
function useForceLayout(nodes, edges, width, height) {
  const posRef = useRef(new Map())
  const activeUntilRef = useRef(0)
  const runningRef = useRef(false)
  const draggingIdRef = useRef(null)
  const settledRef = useRef(false)
  const [, setTick] = useState(0)
  const [settled, setSettled] = useState(false)

  useEffect(() => {
    settledRef.current = false
    setSettled(false)
    const pos = posRef.current
    for (const n of nodes) {
      if (!pos.has(n.id)) {
        pos.set(n.id, {
          x: width / 2 + (Math.random() - 0.5) * 300,
          y: height / 2 + (Math.random() - 0.5) * 300,
          vx: 0,
          vy: 0,
        })
      }
    }
    for (const id of [...pos.keys()]) {
      if (!nodes.some((n) => n.id === id)) pos.delete(id)
    }

    // Per-node radius (same formula the component uses for rendering) so
    // collision avoidance below actually matches what's drawn - without
    // this, hub nodes with many children visually overlap no matter how
    // clean the rest of the layout is.
    const degree = new Map(nodes.map((n) => [n.id, 0]))
    for (const e of edges) {
      if (degree.has(e.source)) degree.set(e.source, degree.get(e.source) + 1)
      if (degree.has(e.target)) degree.set(e.target, degree.get(e.target) + 1)
    }
    const radius = new Map(
      nodes.map((n) => [n.id, (BASE_RADIUS[n.type] || 8) + Math.min(Math.sqrt(degree.get(n.id) || 0) * 3, 14)])
    )
    // Children (memories/action items) sit close to their meeting; people
    // and customer/project links stay looser - Obsidian's clean look comes
    // from short, tight local clusters instead of every edge fighting for
    // the same length.
    const EDGE_DISTANCE = { produced: 55, said: 45, owns: 45, participated_in: 100, for_customer: 110, for_project: 110 }

    function step() {
      const ids = nodes.map((n) => n.id)
      for (let i = 0; i < ids.length; i++) {
        const a = pos.get(ids[i])
        const ra = radius.get(ids[i])
        for (let j = i + 1; j < ids.length; j++) {
          const b = pos.get(ids[j])
          const rb = radius.get(ids[j])
          const dx = a.x - b.x
          const dy = a.y - b.y
          const distSq = Math.max(dx * dx + dy * dy, 1)
          const dist = Math.sqrt(distSq)
          // General repulsion, stronger than before so unconnected clusters
          // actually push apart into visually separate groups instead of
          // blending into one undifferentiated cloud.
          const force = 3200 / distSq
          let fx = (dx / dist) * force
          let fy = (dy / dist) * force
          // Hard collision separation once circles actually overlap -
          // without this, dense hub clusters render as overlapping blobs
          // no matter how the rest of the layout settles.
          const minDist = ra + rb + 6
          if (dist < minDist) {
            const push = (minDist - dist) * 0.5
            fx += (dx / dist) * push
            fy += (dy / dist) * push
          }
          a.vx += fx; a.vy += fy
          b.vx -= fx; b.vy -= fy
        }
      }
      for (const e of edges) {
        const a = pos.get(e.source)
        const b = pos.get(e.target)
        if (!a || !b) continue
        const dx = b.x - a.x
        const dy = b.y - a.y
        const dist = Math.max(Math.sqrt(dx * dx + dy * dy), 1)
        const target = EDGE_DISTANCE[e.type] || 90
        const force = (dist - target) * 0.03
        const fx = (dx / dist) * force
        const fy = (dy / dist) * force
        a.vx += fx; a.vy += fy
        b.vx -= fx; b.vy -= fy
      }
      // Center gravity scaled down as the graph grows - a fixed pull is
      // fine for a handful of nodes but fights the repulsion needed to
      // separate clusters once there are dozens of them.
      const gravity = 0.001 / Math.max(1, Math.sqrt(ids.length / 20))
      let totalSpeed = 0
      for (const id of ids) {
        if (id === draggingIdRef.current) continue
        const p = pos.get(id)
        p.vx += (width / 2 - p.x) * gravity
        p.vy += (height / 2 - p.y) * gravity
        p.vx *= 0.82
        p.vy *= 0.82
        p.x += p.vx
        p.y += p.vy
        p.x = Math.max(20, Math.min(width - 20, p.x))
        p.y = Math.max(20, Math.min(height - 20, p.y))
        totalSpeed += Math.abs(p.vx) + Math.abs(p.vy)
      }
      // Reveal the graph as soon as it's visually calm rather than after a
      // fixed delay - a small graph settles almost instantly (so filtering
      // never shows a spinner) while a dense one gets however long it
      // actually needs instead of being revealed mid-jiggle.
      if (!settledRef.current && ids.length > 0 && totalSpeed / ids.length < 0.12) {
        settledRef.current = true
        setSettled(true)
      }
      setTick((t) => t + 1)
      if (performance.now() < activeUntilRef.current) {
        requestAnimationFrame(step)
      } else {
        runningRef.current = false
        if (!settledRef.current) {
          settledRef.current = true
          setSettled(true)
        }
      }
    }

    activeUntilRef.current = performance.now() + 5500
    runningRef.current = true
    const frame = requestAnimationFrame(step)
    return () => {
      cancelAnimationFrame(frame)
      runningRef.current = false
    }
  }, [nodes, edges, width, height])

  function bump() {
    setTick((t) => t + 1)
  }

  return { positions: posRef.current, draggingIdRef, bump, settled }
}

function NodeDetail({ node, nodes, edges, onOpenNode }) {
  if (!node) {
    return (
      <div className="empty" style={{ padding: '24px 16px' }}>
        Click a node to open it here - a meeting, a person, a decision, an action item.
      </div>
    )
  }

  const byId = useMemo(() => new Map(nodes.map((n) => [n.id, n])), [nodes])
  const related = useMemo(() => {
    const out = []
    for (const e of edges) {
      if (e.source === node.id) out.push({ edge: e, other: byId.get(e.target) })
      else if (e.target === node.id) out.push({ edge: e, other: byId.get(e.source) })
    }
    return out.filter((r) => r.other)
  }, [edges, byId, node.id])

  function relatedByType(type) {
    return related.filter((r) => r.other.type === type)
  }

  return (
    <div className="notebook-detail">
      <div className="detail-meta">
        <span className="tag" style={{ borderColor: COLORS[node.type] }}>{node.type.replace('_', ' ')}</span>
        {node.date && <span className="time">{new Date(node.date).toLocaleString()}</span>}
      </div>
      <h3 style={{ marginTop: 8 }}>{node.label}</h3>

      {node.type === 'meeting' && (
        <>
          <div className="list-item-meta">
            {node.platform && <span className="tag">{node.platform}</span>}
            {node.status && <span className={`badge status-${node.status}`}>{node.status}</span>}
          </div>
          {node.summary ? <p>{node.summary}</p> : <p className="empty">No summary generated yet.</p>}
        </>
      )}

      {node.type === 'memory' && (
        <>
          {node.memory_type && <span className="badge">{node.memory_type}</span>}
          <p>{node.content}</p>
          {node.speaker && <span className="time">— {node.speaker}</span>}
        </>
      )}

      {node.type === 'action_item' && (
        <>
          <div className="list-item-meta">
            {node.status && <span className={`badge status-${node.status}`}>{node.status}</span>}
            {node.priority && <span className="tag">{node.priority}</span>}
            {node.due_date && <span className="tag">due {node.due_date}</span>}
          </div>
          <p>{node.task}</p>
          {node.owner && <span className="time">Owner: {node.owner}</span>}
        </>
      )}

      {(node.type === 'person' || node.type === 'customer' || node.type === 'project') && (
        <p className="subtitle">{related.length} connection{related.length === 1 ? '' : 's'} in the graph.</p>
      )}

      {relatedByType('meeting').length > 0 && node.type !== 'meeting' && (
        <>
          <h4>Meetings</h4>
          <ul className="list">
            {relatedByType('meeting').map(({ other }) => (
              <li key={other.id} className="list-item doc-item" onClick={() => onOpenNode(other)}>
                <div className="list-item-title">{other.label}</div>
              </li>
            ))}
          </ul>
        </>
      )}
      {relatedByType('memory').length > 0 && (
        <>
          <h4>Memories</h4>
          <ul className="list">
            {relatedByType('memory').map(({ other }) => (
              <li key={other.id} className="list-item doc-item" onClick={() => onOpenNode(other)}>
                <div className="list-item-title">{other.label}</div>
              </li>
            ))}
          </ul>
        </>
      )}
      {relatedByType('action_item').length > 0 && (
        <>
          <h4>Action items</h4>
          <ul className="list">
            {relatedByType('action_item').map(({ other }) => (
              <li key={other.id} className="list-item doc-item" onClick={() => onOpenNode(other)}>
                <div className="list-item-title">{other.label}</div>
              </li>
            ))}
          </ul>
        </>
      )}
      {relatedByType('person').length > 0 && (
        <>
          <h4>People</h4>
          <ul className="list">
            {relatedByType('person').map(({ other }) => (
              <li key={other.id} className="list-item doc-item" onClick={() => onOpenNode(other)}>
                <div className="list-item-title">{other.label}</div>
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  )
}

export default function Notebook() {
  const [tab, setTab] = useState('search') // 'search' | 'graph'
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(true)
  const [filter, setFilter] = useState('all')
  const [graphSearch, setGraphSearch] = useState('')
  const [hoveredId, setHoveredId] = useState(null)
  const [selectedId, setSelectedId] = useState(null)
  const [view, setView] = useState({ x: 0, y: 0, k: 1 })
  const [query, setQuery] = useState('')
  const [searching, setSearching] = useState(false)
  const [searchError, setSearchError] = useState(null)
  const [searchResults, setSearchResults] = useState(null)
  const svgRef = useRef(null)
  const panRef = useRef(null)
  const dragRef = useRef(null)
  const width = 1000
  const height = 560

  useEffect(() => {
    getKnowledgeGraph()
      .then(setData)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  const nodes = data?.nodes || []
  const edges = data?.edges || []

  const filteredNodes = useMemo(
    () => (filter === 'all' ? nodes : nodes.filter((n) => n.type === filter)),
    [nodes, filter]
  )
  const filteredEdges = useMemo(() => {
    const ids = new Set(filteredNodes.map((n) => n.id))
    return edges.filter((e) => ids.has(e.source) && ids.has(e.target))
  }, [edges, filteredNodes])

  const degrees = useMemo(() => computeDegrees(filteredNodes, filteredEdges), [filteredNodes, filteredEdges])
  const { positions, draggingIdRef, bump, settled } = useForceLayout(filteredNodes, filteredEdges, width, height)

  // The simulation starts nodes at random positions and throws them around
  // hard before it calms down - showing that raw jiggle looks broken, so an
  // "arranging" overlay covers it until `settled` says the layout is calm.
  // Switching the node-type filter reuses already-settled positions, so it
  // re-settles within a frame or two and the spinner never has time to show.
  const [everSettled, setEverSettled] = useState(false)
  useEffect(() => {
    if (settled) setEverSettled(true)
  }, [settled])
  const layoutReady = everSettled || settled

  const selectedNode = nodes.find((n) => n.id === selectedId) || null

  const neighborIds = new Set()
  if (selectedId) {
    neighborIds.add(selectedId)
    for (const e of filteredEdges) {
      if (e.source === selectedId) neighborIds.add(e.target)
      if (e.target === selectedId) neighborIds.add(e.source)
    }
  }

  // Obsidian-style graph search: a plain substring filter over node
  // labels/content, purely for finding and highlighting nodes already on
  // the canvas - distinct from the Search tab's semantic memory search,
  // which queries the backend and doesn't know about the graph at all.
  const graphMatchIds = useMemo(() => {
    const q = graphSearch.trim().toLowerCase()
    if (!q) return null
    const matches = new Set()
    for (const n of filteredNodes) {
      const haystack = [n.label, n.content, n.task, n.summary, n.speaker, n.owner].filter(Boolean).join(' ').toLowerCase()
      if (haystack.includes(q)) matches.add(n.id)
    }
    return matches
  }, [graphSearch, filteredNodes])

  async function submitSearch(e) {
    e.preventDefault()
    if (!query.trim()) return
    setSearching(true)
    setSearchError(null)
    try {
      const res = await searchMemory(query.trim(), { limit: 15 })
      setSearchResults(res)
    } catch (e) {
      setSearchError(e.message)
    } finally {
      setSearching(false)
    }
  }

  function toGraphSpace(clientX, clientY) {
    const rect = svgRef.current.getBoundingClientRect()
    const svgX = ((clientX - rect.left) / rect.width) * width
    const svgY = ((clientY - rect.top) / rect.height) * height
    return { x: (svgX - view.x) / view.k, y: (svgY - view.y) / view.k }
  }

  function handleWheel(e) {
    const rect = svgRef.current.getBoundingClientRect()
    const cx = ((e.clientX - rect.left) / rect.width) * width
    const cy = ((e.clientY - rect.top) / rect.height) * height
    const factor = e.deltaY < 0 ? 1.12 : 1 / 1.12
    setView((v) => {
      const k = Math.max(0.25, Math.min(3, v.k * factor))
      const x = cx - ((cx - v.x) / v.k) * k
      const y = cy - ((cy - v.y) / v.k) * k
      return { x, y, k }
    })
  }

  // React attaches JSX onWheel as a passive listener, so e.preventDefault()
  // inside it silently does nothing (console even warns about it) - the
  // page scrolls right along with the graph zooming. A native listener
  // registered with { passive: false } is the only way to actually stop
  // that scroll.
  useEffect(() => {
    const el = svgRef.current
    if (!el || tab !== 'graph') return
    function onWheel(e) {
      e.preventDefault()
      handleWheel(e)
    }
    el.addEventListener('wheel', onWheel, { passive: false })
    return () => el.removeEventListener('wheel', onWheel)
  }, [tab, nodes.length])

  function handleBackgroundMouseDown(e) {
    panRef.current = { startX: e.clientX, startY: e.clientY, origin: { ...view } }
  }

  function handleNodeMouseDown(e, node) {
    e.stopPropagation()
    const { x, y } = toGraphSpace(e.clientX, e.clientY)
    const p = positions.get(node.id)
    dragRef.current = { id: node.id, moved: false, offsetX: x - p.x, offsetY: y - p.y }
    draggingIdRef.current = node.id
  }

  function handleMouseMove(e) {
    if (dragRef.current) {
      const d = dragRef.current
      const { x, y } = toGraphSpace(e.clientX, e.clientY)
      const p = positions.get(d.id)
      if (p) {
        p.x = x - d.offsetX
        p.y = y - d.offsetY
        p.vx = 0
        p.vy = 0
        bump()
      }
      d.moved = true
      return
    }
    if (panRef.current) {
      const p = panRef.current
      setView({ ...p.origin, x: p.origin.x + (e.clientX - p.startX), y: p.origin.y + (e.clientY - p.startY) })
    }
  }

  function handleMouseUp(e, node) {
    if (dragRef.current) {
      const wasClick = !dragRef.current.moved
      draggingIdRef.current = null
      dragRef.current = null
      if (wasClick && node) {
        setSelectedId((id) => (id === node.id ? null : node.id))
      }
    }
    panRef.current = null
  }

  return (
    <div className="app">
      <header className="topbar">
        <div>
          <h1>Notebook</h1>
          <p className="subtitle">
            {tab === 'search'
              ? 'Search across every indexed transcript, decision, and note.'
              : 'Click any node to open it - people, meetings, decisions, action items.'}
          </p>
        </div>
      </header>

      <div className="gate-tabs" style={{ maxWidth: 280, marginBottom: 16 }}>
        <button type="button" className={tab === 'search' ? 'active' : ''} onClick={() => setTab('search')}>Search</button>
        <button type="button" className={tab === 'graph' ? 'active' : ''} onClick={() => setTab('graph')}>Graph</button>
      </div>

      {tab === 'search' && (
        <>
          <form className="search-form" onSubmit={submitSearch}>
            <input
              type="text"
              placeholder="e.g. what did we decide about pricing?"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              autoFocus
            />
            <button type="submit" disabled={searching || !query.trim()}>
              {searching ? 'Searching…' : 'Search'}
            </button>
          </form>

          {searchError && <div className="error">Search failed: {searchError}</div>}

          {searchResults && (
            <div className="search-results">
              <h2>{searchResults.total_results} result{searchResults.total_results === 1 ? '' : 's'}</h2>
              {searchResults.results.length === 0 ? (
                <p className="empty">No matches found.</p>
              ) : (
                <ul className="memories">
                  {searchResults.results.map((r) => (
                    <li key={r.id} className="memory-item search-result">
                      <div className="list-item-meta">
                        <span className="badge">{r.memory_type || r.source_type}</span>
                        {r.meeting_title && <span className="tag">{r.meeting_title}</span>}
                        {r.meeting_date && <span className="tag">{r.meeting_date}</span>}
                        {r.project_name && <span className="tag">{r.project_name}</span>}
                        <span className="time">{(r.similarity * 100).toFixed(0)}% match</span>
                      </div>
                      <p>{r.content}</p>
                      {r.speaker && <span className="time">— {r.speaker}</span>}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}
        </>
      )}

      {tab === 'graph' && loading && <div className="loading">Loading graph…</div>}
      {tab === 'graph' && error && <div className="error">Failed to load graph: {error}</div>}
      {tab === 'graph' && !loading && !error && (
        <>
          <div className="topbar-actions" style={{ marginBottom: 14 }}>
            <input
              type="text"
              className="filter-select"
              style={{ minWidth: 220 }}
              placeholder="Search nodes on this graph…"
              value={graphSearch}
              onChange={(e) => setGraphSearch(e.target.value)}
            />
            <select className="filter-select" value={filter} onChange={(e) => setFilter(e.target.value)}>
              <option value="all">All node types</option>
              <option value="meeting">Meetings</option>
              <option value="person">People</option>
              <option value="customer">Customers</option>
              <option value="project">Projects</option>
              <option value="memory">Memories</option>
              <option value="action_item">Action items</option>
            </select>
          </div>

          <div className="notebook-layout">
            {nodes.length === 0 ? (
              <p className="empty">Nothing here yet - meetings need participants, memories, or action items first.</p>
            ) : !layoutReady ? (
              <div className="graph-arranging">
                <div className="graph-arranging-spinner" />
                <span>Arranging graph…</span>
              </div>
            ) : (
              <svg
                ref={svgRef}
                viewBox={`0 0 ${width} ${height}`}
                className="context-graph"
                style={{ maxWidth: '100%', background: '#0a0a0c', borderRadius: 'var(--radius)', border: '1px solid var(--border)', cursor: panRef.current ? 'grabbing' : 'grab' }}
                onMouseDown={handleBackgroundMouseDown}
                onMouseMove={handleMouseMove}
                onMouseUp={() => handleMouseUp()}
                onMouseLeave={() => handleMouseUp()}
              >
                <g transform={`translate(${view.x},${view.y}) scale(${view.k})`}>
                  {filteredEdges.map((e, i) => {
                    const a = positions.get(e.source)
                    const b = positions.get(e.target)
                    if (!a || !b) return null
                    const dimSelection = selectedId && !(neighborIds.has(e.source) && neighborIds.has(e.target))
                    const dimSearch = graphMatchIds && !(graphMatchIds.has(e.source) && graphMatchIds.has(e.target))
                    const dim = dimSelection || dimSearch
                    return <line key={i} x1={a.x} y1={a.y} x2={b.x} y2={b.y} stroke="rgba(255,255,255,0.18)" strokeWidth={1} opacity={dim ? 0.06 : 1} />
                  })}
                  {filteredNodes.map((n) => {
                    const p = positions.get(n.id)
                    if (!p) return null
                    const dimSelection = selectedId && !neighborIds.has(n.id)
                    const dimSearch = graphMatchIds && !graphMatchIds.has(n.id)
                    const dim = dimSelection || dimSearch
                    const degree = degrees.get(n.id) || 0
                    const r = (BASE_RADIUS[n.type] || 8) + Math.min(Math.sqrt(degree) * 3, 14)
                    const isMatch = graphMatchIds && graphMatchIds.has(n.id)
                    const showLabel = view.k > 0.6 || hoveredId === n.id || selectedId === n.id || isMatch
                    return (
                      <g
                        key={n.id}
                        opacity={dim ? 0.12 : 1}
                        onMouseEnter={() => setHoveredId(n.id)}
                        onMouseLeave={() => setHoveredId((id) => (id === n.id ? null : id))}
                        onMouseDown={(e) => handleNodeMouseDown(e, n)}
                        onMouseUp={(e) => { e.stopPropagation(); handleMouseUp(e, n) }}
                        style={{ cursor: 'grab' }}
                      >
                        <circle
                          cx={p.x} cy={p.y} r={r}
                          fill={COLORS[n.type] || '#888'}
                          stroke={selectedId === n.id || isMatch ? '#fff' : 'rgba(0,0,0,0.25)'}
                          strokeWidth={selectedId === n.id || isMatch ? 2 : 1}
                        />
                        {showLabel && (
                          <text x={p.x} y={p.y + r + 11} textAnchor="middle" fill="rgba(255,255,255,0.75)" fontSize="9">
                            {n.label.length > 24 ? `${n.label.slice(0, 24)}…` : n.label}
                          </text>
                        )}
                      </g>
                    )
                  })}
                </g>
              </svg>
            )}

            <div className="notebook-panel">
              <NodeDetail node={selectedNode} nodes={nodes} edges={edges} onOpenNode={(n) => setSelectedId(n.id)} />
            </div>
          </div>

          <div className="list-item-meta" style={{ marginTop: 12 }}>
            {Object.entries(COLORS).map(([type, color]) => (
              <span key={type} className="tag" style={{ borderColor: color }}>
                <span style={{ display: 'inline-block', width: 8, height: 8, borderRadius: '50%', background: color, marginRight: 6 }} />
                {type.replace('_', ' ')}
              </span>
            ))}
          </div>
        </>
      )}
    </div>
  )
}
