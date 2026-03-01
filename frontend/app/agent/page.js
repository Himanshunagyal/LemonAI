'use client'

import { useState, useRef } from 'react'
import { useRouter } from 'next/navigation'
import ProfileCard from '../components/ProfileCard'
import styles from './agent.module.css'

const API = 'https://lemonai-fapu.onrender.com'

const POLL_INTERVAL = 3000  // poll every 3 seconds

export default function AgentPage() {
  const router = useRouter()

  const [persona,     setPersona]     = useState('')
  const [context,     setContext]     = useState('')
  const [maxProfiles, setMaxProfiles] = useState(5)
  const [minScore,    setMinScore]    = useState(5)
  const [loading,     setLoading]     = useState(false)
  const [statusMsg,   setStatusMsg]   = useState('')
  const [statusType,  setStatusType]  = useState('')
  const [results,     setResults]     = useState(null)
  const [errors,      setErrors]      = useState([])

  // Keep reference to polling interval so we can clear it
  const pollRef = useRef(null)

  function stopPolling() {
    if (pollRef.current) {
      clearInterval(pollRef.current)
      pollRef.current = null
    }
  }

  async function runAgent() {
    if (!persona.trim() || !context.trim()) {
      alert('Please fill in both Target Persona and Your Pitch.')
      return
    }

    setLoading(true)
    setStatusType('running')
    setStatusMsg('Starting agent...')
    setResults(null)
    setErrors([])
    stopPolling()

    try {
      // ── STEP 1: Start the job — returns immediately ──
      const res = await fetch(`${API}/jobs`, {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          persona,
          sender_context: context,
          max_profiles:   maxProfiles,
          min_score:      minScore,
        }),
      })

      if (!res.ok) {
        const err = await res.json()
        throw new Error(err.detail || 'Failed to start job')
      }

      const { job_id } = await res.json()
      setStatusMsg(`Job started (ID: ${job_id}). Running pipeline...`)

      // ── STEP 2: Poll every 3 seconds ──
      pollRef.current = setInterval(async () => {
        try {
          const pollRes  = await fetch(`${API}/jobs/${job_id}`)
          const job      = await pollRes.json()

          // Always show the current step from the server
          setStatusMsg(job.current_step)

          // Show partial results as they come in
          if (job.results && job.results.length > 0) {
            setResults(job)
            setErrors(job.errors || [])
          }

          // Job finished
          if (job.status === 'done') {
            stopPolling()
            setLoading(false)
            setStatusType('done')
            setStatusMsg(
              `✓ Done in ${job.duration_seconds}s — ${job.profiles_processed} messages ready, ${job.profiles_skipped} skipped`
            )
            setResults(job)
            setErrors(job.errors || [])
          }

          // Job crashed
          if (job.status === 'error') {
            stopPolling()
            setLoading(false)
            setStatusType('error')
            setStatusMsg(`❌ Error: ${job.error_message}`)
          }

        } catch (pollErr) {
          stopPolling()
          setLoading(false)
          setStatusType('error')
          setStatusMsg('❌ Lost connection to server')
        }
      }, POLL_INTERVAL)

    } catch (err) {
      stopPolling()
      setLoading(false)
      setStatusType('error')
      setStatusMsg('❌ Error: ' + err.message + ' — is your FastAPI server running?')
    }
  }

  async function loadStored() {
    setLoading(true)
    setStatusType('running')
    setStatusMsg('Loading stored profiles...')
    setResults(null)
    stopPolling()

    try {
      const res  = await fetch(`${API}/results`)
      const data = await res.json()

      setResults({
        persona:            'Stored profiles',
        profiles_found:     data.count,
        profiles_processed: data.count,
        profiles_skipped:   0,
        duration_seconds:   0,
        results: data.profiles.map(p => ({
          name:      p.name,
          url:       p.url,
          role:      p.role,
          company:   p.company,
          score:     p.score,
          hook:      p.hook,
          message:   p.message,
          status:    p.status || 'pending',
          timestamp: p.stored_at || '',
        })),
      })
      setStatusType('done')
      setStatusMsg(`✓ Loaded ${data.count} stored profiles`)
    } catch (err) {
      setStatusType('error')
      setStatusMsg('❌ Failed to load: ' + err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className={styles.page}>

      {/* NAV */}
      <nav className={styles.nav}>
        <button className={styles.backBtn} onClick={() => { stopPolling(); router.push('/') }}>
          ← Back
        </button>
        <div className={styles.logo}>Lemon<span>AI</span></div>
        <div className={styles.navStatus}>
          <div className={`${styles.dot} ${styles.dotOnline}`} />
          <span>api connected</span>
        </div>
      </nav>

      <div className={styles.layout}>

        {/* SIDEBAR */}
        <aside className={styles.sidebar}>
          <div>
            <div className={styles.sidebarTitle}>Run Agent</div>
            <div className={styles.sidebarSub}>
              Describe your target and the agent will find, analyze,
              and draft messages for matching LinkedIn profiles.
            </div>
          </div>

          <div className={styles.fieldGroup}>
            <label className={styles.label}>Target Persona *</label>
            <input
              className={styles.input}
              type="text"
              placeholder="ML engineers at Series A startups India"
              value={persona}
              onChange={e => setPersona(e.target.value)}
            />
          </div>

          <div className={styles.fieldGroup}>
            <label className={styles.label}>Your Pitch *</label>
            <textarea
              className={styles.textarea}
              placeholder="I'm building an AI recruiting tool for startups..."
              value={context}
              onChange={e => setContext(e.target.value)}
            />
          </div>

          <div className={styles.fieldGroup}>
            <label className={styles.label}>Max Profiles</label>
            <div className={styles.rangeRow}>
              <input
                type="range" min={1} max={10}
                value={maxProfiles}
                onChange={e => setMaxProfiles(Number(e.target.value))}
                className={styles.range}
              />
              <span className={styles.rangeVal}>{maxProfiles}</span>
            </div>
          </div>

          <div className={styles.fieldGroup}>
            <label className={styles.label}>Min Relevance Score</label>
            <div className={styles.rangeRow}>
              <input
                type="range" min={1} max={10}
                value={minScore}
                onChange={e => setMinScore(Number(e.target.value))}
                className={styles.range}
              />
              <span className={styles.rangeVal}>{minScore}</span>
            </div>
          </div>

          <button
            className={`${styles.runBtn} ${loading ? styles.runBtnLoading : ''}`}
            onClick={runAgent}
            disabled={loading}
          >
            {loading ? '⏳ Running...' : '▶ Run Agent'}
          </button>

          <button
            className={styles.storedBtn}
            onClick={loadStored}
            disabled={loading}
          >
            📋 View Stored Profiles
          </button>
        </aside>

        {/* MAIN */}
        <main className={styles.main}>

          {/* Status bar */}
          {statusType && (
            <div className={`${styles.statusBar} ${styles['status_' + statusType]}`}>
              {statusType === 'running' && <div className={styles.spinner} />}
              <span>{statusMsg}</span>
            </div>
          )}

          {/* Empty state */}
          {!results && !statusType && (
            <div className={styles.emptyState}>
              <div className={styles.emptyIcon}>◈</div>
              <div className={styles.emptyTitle}>No results yet</div>
              <div className={styles.emptySubtitle}>
                Fill in the form and click Run Agent, or view profiles
                already stored from previous runs.
              </div>
            </div>
          )}

          {/* Results */}
          {results && results.results && (
            <div>
              <div className={styles.resultsHeader}>
                <div className={styles.resultsTitle}>
                  Results for &ldquo;{results.persona}&rdquo;
                </div>
                <div className={styles.resultsMeta}>
                  {results.profiles_processed} of {results.profiles_found} profiles processed
                  {loading && ' — updating...'}
                </div>
              </div>

              {results.results.length === 0 ? (
                <div className={styles.noResults}>
                  {loading
                    ? 'Processing profiles...'
                    : 'No profiles passed the filters. Try lowering the minimum score.'}
                </div>
              ) : (
                <div className={styles.grid}>
                  {results.results.map((profile, i) => (
                    <ProfileCard key={profile.url} profile={profile} index={i} />
                  ))}
                </div>
              )}

              {errors.length > 0 && (
                <div className={styles.errorsBox}>
                  <div className={styles.errorsTitle}>⚠ Skipped ({errors.length})</div>
                  {errors.map((e, i) => (
                    <div key={i} className={styles.errorItem}>{e}</div>
                  ))}
                </div>
              )}
            </div>
          )}

        </main>
      </div>
    </div>
  )
}