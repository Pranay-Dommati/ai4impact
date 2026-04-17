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
  case_about: string
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

type OfficerProfile = {
  id: number
  name: string
  username: string
  password: string
  is_active: boolean
  department_name: string
  location_display: string
  active_task_count: number
}

type WorkflowTask = {
  id: number
  complaint: number
  complaint_text: string
  complaint_location: string
  complaint_priority: 'low' | 'medium' | 'high'
  officer: number | null
  officer_name: string
  officer_username: string
  manager: number | null
  manager_name: string
  manager_username: string
  state: 'queued' | 'assigned' | 'in_progress' | 'resolved_pending_verification' | 'closed' | 'escalated'
  sla_due_at: string
  assigned_at: string
  ttr_minutes: number
  escalated_count: number
}

type WorkflowTaskState = WorkflowTask['state']
type ComplaintLifecycleStatus = 'assigned' | 'started_work' | 'completed' | 'closed'

type ActivePage = 'case-file' | 'cases-clusters' | 'location-map' | 'officer-workspace'

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

const workflowLocations = ['Hyderabad - Kokapet', 'Hyderabad - Gachibowli']
const workflowDepartments = ['Road Maintenance', 'Water Department', 'Electricity Department']

function App() {
  const [activePage, setActivePage] = useState<ActivePage>('case-file')
  const [formData, setFormData] = useState(initialForm)
  const [complaints, setComplaints] = useState<Complaint[]>([])
  const [clusters, setClusters] = useState<Cluster[]>([])
  const [officers, setOfficers] = useState<OfficerProfile[]>([])
  const [workflowTasks, setWorkflowTasks] = useState<WorkflowTask[]>([])
  const [selectedOfficerId, setSelectedOfficerId] = useState<number | null>(null)
  const [updatingTaskId, setUpdatingTaskId] = useState<number | null>(null)
  const [latestComplaintId, setLatestComplaintId] = useState<number | null>(null)
  const [sortOrder, setSortOrder] = useState<'latest' | 'oldest' | 'severity_desc'>('latest')
  const [visibleCount, setVisibleCount] = useState<'10' | '25' | 'all'>('25')
  const [caseStatusFilter, setCaseStatusFilter] = useState<'all' | 'open' | 'closed'>('all')
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')

  const workflowTaskByComplaintId = useMemo(
    () => new Map<number, WorkflowTask>(workflowTasks.map((task) => [task.complaint, task])),
    [workflowTasks]
  )

  function getComplaintLifecycleStatus(complaint: Complaint): ComplaintLifecycleStatus {
    const task = workflowTaskByComplaintId.get(complaint.id)
    if (task) {
      if (task.state === 'closed') return 'closed'
      if (task.state === 'resolved_pending_verification') return 'completed'
      if (task.state === 'in_progress') return 'started_work'
      return 'assigned'
    }

    if (complaint.status === 'resolved') {
      return 'closed'
    }
    return 'assigned'
  }

  function getComplaintLifecycleLabel(status: ComplaintLifecycleStatus): string {
    if (status === 'started_work') return 'Started Work'
    if (status === 'completed') return 'Completed'
    if (status === 'closed') return 'Closed'
    return 'Assigned'
  }

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
    const filtered = sortedComplaints.filter((item) => {
      if (caseStatusFilter === 'all') {
        return true
      }
      const status = getComplaintLifecycleStatus(item)
      if (caseStatusFilter === 'closed') {
        return status === 'closed'
      }
      return status !== 'closed'
    })

    if (visibleCount === 'all') {
      return filtered
    }
    return filtered.slice(0, Number(visibleCount))
  }, [sortedComplaints, visibleCount, caseStatusFilter, workflowTaskByComplaintId])

  const portalComplaints = useMemo(
    () => sortedComplaints.filter((item) => item.source === 'portal').slice(0, 8),
    [sortedComplaints]
  )

  const officerMap = useMemo(() => {
    const locations: Record<string, Record<string, OfficerProfile[]>> = {}
    for (const locationName of workflowLocations) {
      locations[locationName] = {}
      for (const departmentName of workflowDepartments) {
        locations[locationName][departmentName] = []
      }
    }

    for (const officer of officers) {
      if (!workflowLocations.includes(officer.location_display)) {
        continue
      }
      if (!workflowDepartments.includes(officer.department_name)) {
        continue
      }
      locations[officer.location_display][officer.department_name].push(officer)
    }

    return workflowLocations.map((locationName) => ({
      location: locationName,
      departments: workflowDepartments.map((departmentName) => ({
        department: departmentName,
        officers: locations[locationName][departmentName].sort((a, b) => a.id - b.id),
      })),
    }))
  }, [officers])

  const selectedOfficer = useMemo(
    () => officers.find((officer) => officer.id === selectedOfficerId) || null,
    [officers, selectedOfficerId]
  )

  const selectedOfficerTasks = useMemo(
    () => workflowTasks.filter((task) => task.officer === selectedOfficerId),
    [workflowTasks, selectedOfficerId]
  )

  const selectedOfficerManagedTasks = useMemo(
    () => workflowTasks.filter((task) => task.manager === selectedOfficerId && task.officer !== selectedOfficerId),
    [workflowTasks, selectedOfficerId]
  )

  const officerTaskStats = useMemo(() => {
    const assigned = selectedOfficerTasks.filter((task) => task.state === 'assigned').length
    const inProgress = selectedOfficerTasks.filter((task) => task.state === 'in_progress').length
    const awaitingVerification = selectedOfficerTasks.filter((task) => task.state === 'resolved_pending_verification').length
    const escalated = selectedOfficerTasks.filter((task) => task.state === 'escalated').length
    const closed = selectedOfficerTasks.filter((task) => task.state === 'closed').length
    const active = selectedOfficerTasks.filter((task) => task.state !== 'closed').length
    return { assigned, inProgress, awaitingVerification, escalated, closed, active }
  }, [selectedOfficerTasks])

  async function fetchData(options?: { initialLoad?: boolean }) {
    try {
      setError('')
      if (options?.initialLoad) {
        setLoading(true)
      }
      const [complaintsRes, clustersRes, officersRes, workflowTasksRes] = await Promise.all([
        fetch('/api/complaints/'),
        fetch('/api/clusters/'),
        fetch('/api/workflow/officers/'),
        fetch('/api/workflow/tasks/'),
      ])

      if (!complaintsRes.ok || !clustersRes.ok) {
        throw new Error('Failed to load data from API.')
      }

      const [complaintsData, clustersData] = await Promise.all([
        complaintsRes.json(),
        clustersRes.json(),
      ])

      const officersData = officersRes.ok ? await officersRes.json() : []
      const workflowTaskData = workflowTasksRes.ok ? await workflowTasksRes.json() : []

      setComplaints((prev) => {
        const previousTopId = prev[0]?.id
        const incomingTopId = complaintsData[0]?.id
        if (previousTopId && incomingTopId && previousTopId !== incomingTopId) {
          setLatestComplaintId(incomingTopId)
        }
        return complaintsData
      })
      setClusters(clustersData)
      setOfficers(officersData)
      setWorkflowTasks(workflowTaskData)

      if (selectedOfficerId && !officersData.some((officer: OfficerProfile) => officer.id === selectedOfficerId)) {
        setSelectedOfficerId(null)
      }
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

  useEffect(() => {
    if (activePage === 'officer-workspace' && !selectedOfficerId) {
      setActivePage('location-map')
    }
  }, [activePage, selectedOfficerId])

  function openOfficerWorkspace(officerId: number) {
    setSelectedOfficerId(officerId)
    setActivePage('officer-workspace')
  }

  async function markTaskCompleted(taskId: number) {
    await transitionTask(taskId, 'resolved_pending_verification')
  }

  async function transitionTask(taskId: number, state: WorkflowTaskState) {
    if (!selectedOfficer) {
      return
    }

    try {
      setUpdatingTaskId(taskId)
      setError('')

      const response = await fetch(`/api/workflow/tasks/${taskId}/transition/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          state,
          actor: selectedOfficer.username,
        }),
      })

      if (!response.ok) {
        const payload = await response.json().catch(() => ({}))
        throw new Error(payload?.detail || 'Failed to update task state')
      }

      await fetchData()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unexpected error while updating task state')
    } finally {
      setUpdatingTaskId(null)
    }
  }

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
          Locations {'>'} Departments {'>'} Officers
        </button>
        {selectedOfficer && (
          <button
            className={activePage === 'officer-workspace' ? 'nav-btn active' : 'nav-btn'}
            onClick={() => setActivePage('officer-workspace')}
          >
            Officer Workspace
          </button>
        )}
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
                <label>
                  Complaint Status
                  <select value={caseStatusFilter} onChange={(event) => setCaseStatusFilter(event.target.value as 'all' | 'open' | 'closed')}>
                    <option value="all">All</option>
                    <option value="open">Open</option>
                    <option value="closed">Closed</option>
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
                      <th>Status</th>
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
                        <td>
                          <span className={`status-badge status-${getComplaintLifecycleStatus(item)}`}>
                            {getComplaintLifecycleLabel(getComplaintLifecycleStatus(item))}
                          </span>
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
                      <strong>Case About:</strong> {cluster.case_about}
                    </p>
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
        </>
      )}

      {activePage === 'location-map' && (
        <section className="card">
          <h2>Location {'>'} Department {'>'} Officers</h2>
          <p className="section-note">Showing only seeded workflow map: Hyderabad - Kokapet and Hyderabad - Gachibowli, each with 3 departments and officer IDs.</p>
          {loading ? (
            <p>Loading map...</p>
          ) : officerMap.length === 0 ? (
            <p>No officer roster data available.</p>
          ) : (
            <>
              <div className="tree-grid">
              {officerMap.map((locationItem) => (
                <article key={locationItem.location} className="tree-card">
                  <header className="tree-header">
                    <h3>{locationItem.location}</h3>
                    <span className="tree-count">{locationItem.departments.reduce((acc, row) => acc + row.officers.length, 0)} officers</span>
                  </header>
                  <div className="tree-departments">
                    {locationItem.departments.map((departmentItem) => (
                      <details key={`${locationItem.location}-${departmentItem.department}`} className="tree-department">
                        <summary>
                          <span>{departmentItem.department}</span>
                          <span>{departmentItem.officers.length}</span>
                        </summary>
                        <ul className="tree-cases">
                          {departmentItem.officers.map((officer) => (
                            <li key={officer.id}>
                              <p className="tree-case-text">Officer ID: {officer.id} | {officer.name}</p>
                              <p className="mini-text">Login: {officer.username} / {officer.password} | Active Cases: {officer.active_task_count}</p>
                              <button className="officer-login-btn" onClick={() => openOfficerWorkspace(officer.id)}>
                                Login As Officer
                              </button>
                            </li>
                          ))}
                        </ul>
                      </details>
                    ))}
                  </div>
                </article>
              ))}
              </div>
            </>
          )}
        </section>
      )}

      {activePage === 'officer-workspace' && (
        <section className="card officer-page-card">
          {!selectedOfficer ? (
            <div>
              <h2>Officer Workspace</h2>
              <p className="section-note">No officer selected. Please choose Login As Officer from the map.</p>
              <button className="officer-secondary-btn" onClick={() => setActivePage('location-map')}>
                Back To Location Map
              </button>
            </div>
          ) : (
            <section className="officer-dashboard">
              <div className="officer-dashboard-header">
                <h3>Officer Dashboard</h3>
                <button
                  className="officer-logout-btn"
                  onClick={() => {
                    setSelectedOfficerId(null)
                    setActivePage('location-map')
                  }}
                >
                  Exit
                </button>
              </div>
              <div className="officer-profile-grid">
                <div className="officer-profile-card">
                  <p><strong>ID:</strong> {selectedOfficer.id}</p>
                  <p><strong>Name:</strong> {selectedOfficer.name}</p>
                  <p><strong>Username:</strong> {selectedOfficer.username}</p>
                  <p><strong>Department:</strong> {selectedOfficer.department_name}</p>
                  <p><strong>Location:</strong> {selectedOfficer.location_display}</p>
                </div>
                <div className="officer-profile-card">
                  <p><strong>Currently Active:</strong> {officerTaskStats.active}</p>
                  <p><strong>Assigned:</strong> {officerTaskStats.assigned}</p>
                  <p><strong>In Progress:</strong> {officerTaskStats.inProgress}</p>
                  <p><strong>Awaiting Verification:</strong> {officerTaskStats.awaitingVerification}</p>
                  <p><strong>Escalated:</strong> {officerTaskStats.escalated}</p>
                  <p><strong>Closed:</strong> {officerTaskStats.closed}</p>
                </div>
                <div className="officer-profile-card">
                  <p><strong>Active Cases (API):</strong> {selectedOfficer.active_task_count}</p>
                  <p><strong>Total Cases Handled:</strong> {selectedOfficerTasks.length}</p>
                  <p><strong>Manager Cases:</strong> {selectedOfficerManagedTasks.length}</p>
                  <p><strong>Status:</strong> {selectedOfficer.is_active ? 'Active' : 'Inactive'}</p>
                  <p className="mini-text">
                    Use Start Work {'>'} Mark Completed to trigger citizen Telegram verification.
                  </p>
                </div>
              </div>

              <div className="officer-section-header">
                <h4>My Cases</h4>
              </div>

              {selectedOfficerTasks.length === 0 ? (
                <p>No assigned cases for this officer.</p>
              ) : (
                <div className="officer-task-list">
                  {selectedOfficerTasks.map((task) => (
                    <article key={task.id} className="officer-task-item">
                      <p className="tree-case-text">Case #{task.complaint} - {task.complaint_text}</p>
                      <p className="mini-text">
                        Task #{task.id} | State: {task.state} | Priority: {task.complaint_priority.toUpperCase()} | SLA: {new Date(task.sla_due_at).toLocaleString()}
                      </p>
                      <p className="mini-text">
                        Assigned: {new Date(task.assigned_at).toLocaleString()} | Escalations: {task.escalated_count} | Manager: {task.manager_name || 'None'}
                      </p>

                      <div className="officer-action-row">
                        {task.state === 'assigned' && (
                          <button
                            className="officer-secondary-btn"
                            onClick={() => transitionTask(task.id, 'in_progress')}
                            disabled={updatingTaskId === task.id}
                          >
                            {updatingTaskId === task.id ? 'Submitting...' : 'Start Work'}
                          </button>
                        )}

                        {(task.state === 'assigned' || task.state === 'in_progress' || task.state === 'escalated') && (
                          <button
                            className="officer-complete-btn"
                            onClick={() => markTaskCompleted(task.id)}
                            disabled={updatingTaskId === task.id}
                          >
                            {updatingTaskId === task.id ? 'Submitting...' : 'Mark Completed'}
                          </button>
                        )}

                        {(task.state === 'in_progress' || task.state === 'resolved_pending_verification') && (
                          <button
                            className="officer-warning-btn"
                            onClick={() => transitionTask(task.id, 'escalated')}
                            disabled={updatingTaskId === task.id}
                          >
                            {updatingTaskId === task.id ? 'Submitting...' : 'Escalate'}
                          </button>
                        )}
                      </div>

                      {task.state === 'resolved_pending_verification' && (
                        <p className="mini-text officer-task-hint">
                          Citizen verification prompt sent on Telegram.
                        </p>
                      )}
                    </article>
                  ))}
                </div>
              )}

              {selectedOfficerManagedTasks.length > 0 && (
                <>
                  <div className="officer-section-header">
                    <h4>Escalations Assigned As Manager</h4>
                  </div>
                  <div className="officer-task-list">
                    {selectedOfficerManagedTasks.map((task) => (
                      <article key={`managed-${task.id}`} className="officer-task-item">
                        <p className="tree-case-text">Task #{task.id} | Case #{task.complaint} - {task.complaint_text}</p>
                        <p className="mini-text">
                          Officer: {task.officer_name || 'Unassigned'} | State: {task.state} | Priority: {task.complaint_priority.toUpperCase()} | SLA: {new Date(task.sla_due_at).toLocaleString()}
                        </p>
                      </article>
                    ))}
                  </div>
                </>
              )}
            </section>
          )}
        </section>
      )}
    </main>
  )
}

export default App
