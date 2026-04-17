import { useEffect, useMemo, useState } from 'react'
import './App.css'

type Complaint = {
  id: number
  text: string
  category: string
  location: string
  source: string
  priority: 'low' | 'medium' | 'high'
  score: number
  impact_score: number
  severity: 'low' | 'medium' | 'high'
  urgency: 'low' | 'medium' | 'high'
  risk_type: string
  affected_population_estimate: number
  duration_hint: string
  issue_type: string
  cluster_id: string
  ai_confidence: number
  assigned_department_name: string
  routing: {
    department?: string
    sub_department?: string
    jurisdiction?: string
  }
  reasoning: string[]
  status: 'pending' | 'resolved'
  created_at: string
}

type Cluster = {
  cluster_id: string
  total_complaints: number
  category: string
  location: string
  impact: 'LOW' | 'MEDIUM' | 'HIGH'
  impact_score: number
  estimated_people: number
  insight: string
  assigned_department: string
  priority_breakdown: {
    high: number
    medium: number
    low: number
  }
  severity_breakdown: {
    high: number
    medium: number
    low: number
  }
}

type ActivePage = 'case-file' | 'cases-clusters' | 'location-map'

const initialForm = {
  text: '',
  category: '',
  location: '',
  locationType: '',
}

const sourceLabels: Record<string, string> = {
  portal: 'Portal Submission',
  telegram: 'Telegram Bot',
}

const locationTypeLabels: Record<string, string> = {
  road: 'Road',
  school: 'School',
  hospital: 'Hospital',
  residential: 'Residential',
}

function App() {
  const [activePage, setActivePage] = useState<ActivePage>('case-file')
  const [formData, setFormData] = useState(initialForm)
  const [complaints, setComplaints] = useState<Complaint[]>([])
  const [clusters, setClusters] = useState<Cluster[]>([])
  const [latestComplaintId, setLatestComplaintId] = useState<number | null>(null)
  const [sortOrder, setSortOrder] = useState<'latest' | 'oldest' | 'severity_desc'>('latest')
  const [visibleCount, setVisibleCount] = useState<'10' | '25' | 'all'>('25')
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')

  const totals = useMemo(() => {
    const totalComplaints = complaints.length
    const highPriority = complaints.filter((item) => item.priority === 'high').length
    const mediumPriority = complaints.filter((item) => item.priority === 'medium').length
    const lowPriority = complaints.filter((item) => item.priority === 'low').length
    return { totalComplaints, highPriority, mediumPriority, lowPriority }
  }, [complaints])

  const sortedComplaints = useMemo(() => {
    const severityRank: Record<Complaint['severity'], number> = {
      high: 3,
      medium: 2,
      low: 1,
    }

    return [...complaints].sort((a, b) => {
      const aTime = new Date(a.created_at).getTime()
      const bTime = new Date(b.created_at).getTime()
      if (sortOrder === 'latest') {
        return bTime - aTime
      }
      if (sortOrder === 'oldest') {
        return aTime - bTime
      }

      const severityDelta = severityRank[b.severity] - severityRank[a.severity]
      if (severityDelta !== 0) {
        return severityDelta
      }
      return bTime - aTime
    })
  }, [complaints, sortOrder])

  const visibleComplaints = useMemo(() => {
    if (visibleCount === 'all') {
      return sortedComplaints
    }
    return sortedComplaints.slice(0, Number(visibleCount))
  }, [sortedComplaints, visibleCount])

  const portalComplaints = useMemo(
    () => sortedComplaints.filter((item) => item.source === 'portal').slice(0, 8),
    [sortedComplaints]
  )

  const locationDepartmentCases = useMemo(() => {
    const grouped: Record<string, Record<string, Complaint[]>> = {}

    for (const item of sortedComplaints) {
      const locationKey = item.location || 'Unknown Location'
      const departmentKey = item.assigned_department_name || 'Unassigned'
      if (!grouped[locationKey]) {
        grouped[locationKey] = {}
      }
      if (!grouped[locationKey][departmentKey]) {
        grouped[locationKey][departmentKey] = []
      }
      grouped[locationKey][departmentKey].push(item)
    }

    return Object.entries(grouped)
      .map(([location, departments]) => {
        const departmentRows = Object.entries(departments)
          .map(([department, cases]) => ({
            department,
            cases,
          }))
          .sort((a, b) => b.cases.length - a.cases.length)

        const totalCases = departmentRows.reduce((acc, row) => acc + row.cases.length, 0)
        return {
          location,
          departments: departmentRows,
          totalCases,
        }
      })
      .sort((a, b) => b.totalCases - a.totalCases)
  }, [sortedComplaints])

  async function fetchData(options?: { initialLoad?: boolean }) {
    try {
      setError('')
      if (options?.initialLoad) {
        setLoading(true)
      }
      const [complaintsRes, clustersRes] = await Promise.all([
        fetch('/api/complaints/'),
        fetch('/api/clusters/'),
      ])

      if (!complaintsRes.ok || !clustersRes.ok) {
        throw new Error('Failed to load data from API.')
      }

      const [complaintsData, clustersData] = await Promise.all([
        complaintsRes.json(),
        clustersRes.json(),
      ])

      setComplaints((prev) => {
        const previousTopId = prev[0]?.id
        const incomingTopId = complaintsData[0]?.id
        if (previousTopId && incomingTopId && previousTopId !== incomingTopId) {
          setLatestComplaintId(incomingTopId)
        }
        return complaintsData
      })
      setClusters(clustersData)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unexpected error')
    } finally {
      if (options?.initialLoad) {
        setLoading(false)
      }
    }
  }

  useEffect(() => {
    fetchData({ initialLoad: true })
    const interval = window.setInterval(() => {
      fetchData()
    }, 3000)

    return () => window.clearInterval(interval)
  }, [])

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    try {
      setSubmitting(true)
      setError('')

      const response = await fetch('/api/complaints/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          text: formData.locationType
            ? `${formData.text} (Location Type: ${locationTypeLabels[formData.locationType]})`
            : formData.text,
          category: formData.category || 'other',
          location: formData.location,
          source: 'portal',
        }),
      })

      if (!response.ok) {
        const detail = await response.text()
        throw new Error(detail || 'Failed to create complaint.')
      }

      setFormData(initialForm)
      await fetchData()
      setActivePage('cases-clusters')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unexpected error')
    } finally {
      setSubmitting(false)
    }
  }

  function setField(field: keyof typeof initialForm, value: string) {
    setFormData((prev) => ({ ...prev, [field]: value }))
  }

  return (
    <main className="page">
      <header className="hero">
        <p className="eyebrow">Civix-Pulse</p>
        <h1>AI-Powered Grievance Intelligence</h1>
        <p className="subtitle">Case File | Cases & Clusters | Location Department Map</p>
      </header>

      {error && <div className="alert">{error}</div>}

      <section className="stats-grid">
        <article className="card stat">
          <h3>Total Complaints</h3>
          <p>{totals.totalComplaints}</p>
        </article>
        <article className="card stat high">
          <h3>High Priority</h3>
          <p>{totals.highPriority}</p>
        </article>
        <article className="card stat medium">
          <h3>Medium Priority</h3>
          <p>{totals.mediumPriority}</p>
        </article>
        <article className="card stat low">
          <h3>Low Priority</h3>
          <p>{totals.lowPriority}</p>
        </article>
      </section>

      <nav className="card page-nav" aria-label="Main pages">
        <button
          className={activePage === 'case-file' ? 'nav-btn active' : 'nav-btn'}
          onClick={() => setActivePage('case-file')}
        >
          Case File (Portal)
        </button>
        <button
          className={activePage === 'cases-clusters' ? 'nav-btn active' : 'nav-btn'}
          onClick={() => setActivePage('cases-clusters')}
        >
          Cases & Clusters
        </button>
        <button
          className={activePage === 'location-map' ? 'nav-btn active' : 'nav-btn'}
          onClick={() => setActivePage('location-map')}
        >
          Locations {'>'} Departments {'>'} Cases
        </button>
      </nav>

      {activePage === 'case-file' && (
        <section className="layout">
          <article className="card">
            <h2>Portal Case File</h2>
            <p className="section-note">Create portal-origin cases with structured metadata and AI routing.</p>
            <form onSubmit={handleSubmit} className="form">
              <label>
                Complaint Description *
                <textarea
                  value={formData.text}
                  onChange={(event) => setField('text', event.target.value)}
                  placeholder="Example: Street lights not working in Kokapet near school since 2 days"
                  required
                />
              </label>

              <label>
                Category (optional)
                <select
                  value={formData.category}
                  onChange={(event) => setField('category', event.target.value)}
                >
                  <option value="">Auto-detect / Others</option>
                  <option value="water">Water</option>
                  <option value="electricity">Electricity</option>
                  <option value="roads">Roads</option>
                  <option value="other">Others</option>
                </select>
              </label>

              <label>
                Area / Location *
                <input
                  value={formData.location}
                  onChange={(event) => setField('location', event.target.value)}
                  placeholder="Kokapet"
                  required
                />
              </label>

              <label>
                Location Type (optional)
                <select
                  value={formData.locationType}
                  onChange={(event) => setField('locationType', event.target.value)}
                >
                  <option value="">Select type</option>
                  <option value="road">Road</option>
                  <option value="school">School</option>
                  <option value="hospital">Hospital</option>
                  <option value="residential">Residential</option>
                </select>
              </label>

              <button type="submit" disabled={submitting}>
                {submitting ? 'Submitting...' : 'Create Portal Case'}
              </button>
            </form>
          </article>

          <article className="card">
            <h2>Recent Portal Cases</h2>
            {loading ? (
              <p>Loading portal cases...</p>
            ) : portalComplaints.length === 0 ? (
              <p>No portal cases yet.</p>
            ) : (
              <ul className="cluster-list">
                {portalComplaints.map((item) => (
                  <li key={item.id} className="cluster-item">
                    <div className="cluster-top">
                      <strong>{item.location}</strong>
                      <span className={`priority ${item.priority}`}>{item.priority.toUpperCase()}</span>
                    </div>
                    <p>{item.text}</p>
                    <p>
                      Dept: {item.assigned_department_name} | Score: {item.score} | Impact: {item.impact_score}
                    </p>
                    <p className="mini-text">AI Confidence: {(item.ai_confidence * 100).toFixed(0)}%</p>
                  </li>
                ))}
              </ul>
            )}
          </article>
        </section>
      )}

      {activePage === 'cases-clusters' && (
        <>
          <section className="card">
            <h2>Cluster Insights</h2>
            {loading ? (
              <p>Loading clusters...</p>
            ) : (
              <ul className="cluster-list">
                {clusters.map((cluster) => (
                  <li key={cluster.cluster_id} className="cluster-item">
                    <div className="cluster-top">
                      <strong>{cluster.location}</strong>
                      <span className={`impact ${cluster.impact.toLowerCase()}`}>{cluster.impact}</span>
                    </div>
                    <p>
                      {cluster.category} | Count: {cluster.total_complaints} | Estimated People: {cluster.estimated_people}
                    </p>
                    <p>
                      Impact Score: {cluster.impact_score} | H/M/L: {cluster.priority_breakdown.high}/
                      {cluster.priority_breakdown.medium}/{cluster.priority_breakdown.low}
                    </p>
                    <p>
                      Severity H/M/L: {cluster.severity_breakdown.high}/{cluster.severity_breakdown.medium}/
                      {cluster.severity_breakdown.low} | Department: {cluster.assigned_department}
                    </p>
                    <p className="insight">{cluster.insight}</p>
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section className="card">
            <div className="feed-header">
              <h2>Cases Feed</h2>
              <div className="feed-controls">
                <label>
                  Order
                  <select
                    value={sortOrder}
                    onChange={(event) => setSortOrder(event.target.value as 'latest' | 'oldest' | 'severity_desc')}
                  >
                    <option value="latest">Latest first</option>
                    <option value="oldest">Oldest first</option>
                    <option value="severity_desc">Severity (High to Low)</option>
                  </select>
                </label>
                <label>
                  Show
                  <select value={visibleCount} onChange={(event) => setVisibleCount(event.target.value as '10' | '25' | 'all')}>
                    <option value="10">Latest 10</option>
                    <option value="25">Latest 25</option>
                    <option value="all">All</option>
                  </select>
                </label>
                <span className="live-tag">Live Feed (Auto-updating every 3s)</span>
              </div>
            </div>
            {loading ? (
              <p>Loading complaints...</p>
            ) : (
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Text</th>
                      <th>Category</th>
                      <th>Location</th>
                      <th>Source</th>
                      <th>Priority</th>
                      <th>Severity / Urgency</th>
                      <th>Department</th>
                      <th>Score</th>
                      <th>Impact</th>
                      <th>AI Reasoning</th>
                    </tr>
                  </thead>
                  <tbody>
                    {visibleComplaints.map((item) => (
                      <tr key={item.id} className={latestComplaintId === item.id ? 'new-item' : ''}>
                        <td>{item.text}</td>
                        <td>{item.category}</td>
                        <td>{item.location}</td>
                        <td>
                          <span className={`source source-${item.source}`}>
                            {sourceLabels[item.source] || item.source}
                          </span>
                        </td>
                        <td>
                          <span className={`priority ${item.priority}`}>{item.priority.toUpperCase()}</span>
                        </td>
                        <td>
                          <span className={`priority ${item.severity}`}>{item.severity.toUpperCase()}</span>
                          {' / '}
                          <span className={`priority ${item.urgency}`}>{item.urgency.toUpperCase()}</span>
                        </td>
                        <td>
                          {item.assigned_department_name}
                          <div className="mini-text">
                            {item.routing?.sub_department || 'General'} | {item.routing?.jurisdiction || item.location}
                          </div>
                        </td>
                        <td>{item.score}</td>
                        <td>
                          {item.impact_score}
                          <div className="mini-text">AI: {(item.ai_confidence * 100).toFixed(0)}%</div>
                        </td>
                        <td>
                          <ul className="reason-list">
                            {(item.reasoning || []).slice(0, 2).map((reason) => (
                              <li key={reason}>{reason}</li>
                            ))}
                          </ul>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        </>
      )}

      {activePage === 'location-map' && (
        <section className="card">
          <h2>Location {'>'} Department {'>'} Cases</h2>
          <p className="section-note">Browse case ownership by location, then drill down into assigned departments and cases.</p>
          {loading ? (
            <p>Loading map...</p>
          ) : locationDepartmentCases.length === 0 ? (
            <p>No cases available.</p>
          ) : (
            <div className="tree-grid">
              {locationDepartmentCases.map((locationItem) => (
                <article key={locationItem.location} className="tree-card">
                  <header className="tree-header">
                    <h3>{locationItem.location}</h3>
                    <span className="tree-count">{locationItem.totalCases} cases</span>
                  </header>
                  <div className="tree-departments">
                    {locationItem.departments.map((departmentItem) => (
                      <details key={`${locationItem.location}-${departmentItem.department}`} className="tree-department">
                        <summary>
                          <span>{departmentItem.department}</span>
                          <span>{departmentItem.cases.length}</span>
                        </summary>
                        <ul className="tree-cases">
                          {departmentItem.cases.map((item) => (
                            <li key={item.id}>
                              <p className="tree-case-text">{item.text}</p>
                              <p className="mini-text">
                                {item.priority.toUpperCase()} | Score {item.score} | {item.source}
                              </p>
                            </li>
                          ))}
                        </ul>
                      </details>
                    ))}
                  </div>
                </article>
              ))}
            </div>
          )}
        </section>
      )}
    </main>
  )
}

export default App
