// Client-side keyword extraction + a small force-free radial graph, built
// entirely from data the meeting detail view already has (summary, memories,
// action items, platform/started_at) - no backend round trip needed.

const STOPWORDS = new Set([
  'the', 'a', 'an', 'and', 'or', 'but', 'if', 'then', 'so', 'to', 'of', 'in',
  'on', 'at', 'for', 'with', 'about', 'as', 'by', 'from', 'is', 'are', 'was',
  'were', 'be', 'been', 'being', 'this', 'that', 'these', 'those', 'it', 'its',
  'we', 'they', 'he', 'she', 'you', 'i', 'our', 'their', 'his', 'her', 'my',
  'will', 'would', 'should', 'could', 'can', 'may', 'might', 'shall', 'not',
  'no', 'do', 'does', 'did', 'have', 'has', 'had', 'up', 'out', 'into', 'over',
  'also', 'just', 'than', 'there', 'here', 'what', 'when', 'where', 'which',
  'who', 'how', 'all', 'any', 'some', 'each', 'more', 'most', 'other', 'such',
  'only', 'own', 'same', 'too', 'very', 'still', 'now', 'again', 'us', 'them',
])

function extractKeywords(text, limit = 10) {
  const counts = new Map()
  const words = (text || '').toLowerCase().match(/[a-z][a-z0-9'-]{2,}/g) || []
  for (const w of words) {
    if (STOPWORDS.has(w)) continue
    counts.set(w, (counts.get(w) || 0) + 1)
  }
  return [...counts.entries()]
    .sort((a, b) => b[1] - a[1])
    .slice(0, limit)
    .map(([word, count]) => ({ word, count }))
}

export function highlightKeywords(text, keywords) {
  if (!text || keywords.length === 0) return text
  const pattern = new RegExp(`\\b(${keywords.map((k) => k.word).join('|')})\\b`, 'gi')
  const parts = text.split(pattern)
  return parts.map((part, i) => {
    const isKeyword = keywords.some((k) => k.word === part.toLowerCase())
    return isKeyword ? <mark key={i} className="keyword-mark">{part}</mark> : part
  })
}

const COLORS = ['#ff8a3d', '#ffb677', '#7fb2ff', '#8fd6a8', '#e69be6', '#ffd166', '#6ee7d0', '#f28ba0']

export default function ContextGraph({ meeting }) {
  const sourceText = [
    meeting.summary,
    ...meeting.memories.map((m) => m.content),
    ...(meeting.action_items || []).map((a) => a.task),
  ].filter(Boolean).join('. ')

  const keywords = extractKeywords(sourceText, 8)

  const started = meeting.started_at ? new Date(meeting.started_at) : null
  const metaNodes = [
    { label: 'Day', value: started ? started.toLocaleDateString(undefined, { weekday: 'long', month: 'short', day: 'numeric' }) : '—' },
    { label: 'Time', value: started ? started.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' }) : '—' },
    { label: 'Mode', value: meeting.platform || '—' },
  ]

  const width = 640
  const height = 480
  const cx = width / 2
  const cy = 230
  const centerLabel = meeting.title || 'Meeting'

  // Metadata nodes sit in a straight row above the center node, evenly
  // spaced regardless of how many there are - an arc looked natural for
  // many nodes but bunched three together into an unreadable overlap.
  const metaY = 50
  const metaSpacing = 150
  const metaPositions = metaNodes.map((n, i) => ({
    ...n,
    x: cx + (i - (metaNodes.length - 1) / 2) * metaSpacing,
    y: metaY,
  }))

  // Keywords fan out in an arc below the center, staying clear of the
  // metadata row above so nothing overlaps.
  const kwRadius = 160
  const kwArcStart = Math.PI * 0.15
  const kwArcEnd = Math.PI * 1.85
  const kwPositions = keywords.map((k, i) => {
    const t = keywords.length > 1 ? i / (keywords.length - 1) : 0.5
    const angle = kwArcStart + t * (kwArcEnd - kwArcStart)
    return { ...k, x: cx + kwRadius * Math.cos(angle), y: cy + 50 + kwRadius * Math.sin(angle) }
  })

  if (keywords.length === 0 && !started && !meeting.platform) {
    return <p className="empty">Not enough meeting content yet to build a context graph.</p>
  }

  return (
    <svg viewBox={`0 0 ${width} ${height}`} className="context-graph" role="img" aria-label="Meeting context graph">
      {metaPositions.map((n, i) => (
        <line key={`meta-line-${i}`} x1={cx} y1={cy} x2={n.x} y2={n.y} className="graph-edge graph-edge-meta" />
      ))}
      {kwPositions.map((n, i) => (
        <line key={`kw-line-${i}`} x1={cx} y1={cy} x2={n.x} y2={n.y} className="graph-edge" stroke={COLORS[i % COLORS.length]} />
      ))}

      <circle cx={cx} cy={cy} r={44} className="graph-node graph-node-center" />
      <text x={cx} y={cy - 4} textAnchor="middle" className="graph-label graph-label-center">Meeting</text>
      <text x={cx} y={cy + 14} textAnchor="middle" className="graph-label graph-label-center-sub">
        {centerLabel.length > 18 ? `${centerLabel.slice(0, 18)}…` : centerLabel}
      </text>

      {metaPositions.map((n, i) => (
        <g key={`meta-${i}`}>
          <rect x={n.x - 60} y={n.y - 18} width={120} height={36} rx={8} className="graph-node graph-node-meta" />
          <text x={n.x} y={n.y - 3} textAnchor="middle" className="graph-label graph-label-meta-title">{n.label}</text>
          <text x={n.x} y={n.y + 12} textAnchor="middle" className="graph-label graph-label-meta-value">{n.value}</text>
        </g>
      ))}

      {kwPositions.map((n, i) => (
        <g key={`kw-${i}`}>
          <circle cx={n.x} cy={n.y} r={26 + Math.min(n.count, 4) * 2} fill={COLORS[i % COLORS.length]} className="graph-node graph-node-kw" />
          <text x={n.x} y={n.y + 4} textAnchor="middle" className="graph-label graph-label-kw">{n.word}</text>
        </g>
      ))}
    </svg>
  )
}

export { extractKeywords }
