'use client'

import { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import styles from './page.module.css'

const API = 'https://lemonai-fapu.onrender.com'

export default function HomePage() {
  const router = useRouter()
  const [apiStatus, setApiStatus] = useState('checking...')
  const [apiOnline, setApiOnline] = useState(false)
  const [stats, setStats] = useState(null)

  useEffect(() => {
    checkApi()
  }, [])

  async function checkApi() {
    try {
      const res = await fetch(`${API}/health`)
      if (res.ok) {
        setApiOnline(true)
        setApiStatus('api connected')
        loadStats()
      }
    } catch {
      setApiStatus('api offline — start FastAPI server')
    }
  }

  async function loadStats() {
    try {
      const res  = await fetch(`${API}/stats`)
      const data = await res.json()
      if (data.total_profiles > 0) setStats(data)
    } catch {}
  }

  return (
    <div className={styles.page}>

      {/* ── NAV ── */}
      <nav className={styles.nav}>
        <div className={styles.logo}>Lemon<span>AI</span></div>
        <div className={styles.navStatus}>
          <div className={`${styles.dot} ${apiOnline ? styles.dotOnline : ''}`} />
          <span>{apiStatus}</span>
        </div>
      </nav>

      {/* ── HERO ── */}
      <section className={styles.hero}>
        <div className={styles.heroGlow} />

        <div className={styles.heroContent}>

          <h1 className={styles.h1}>
            <span className={styles.line1}>Find the right</span>
            <span className={styles.line2}>people, faster.</span>
            <span className={styles.line3}>Automatically.</span>
          </h1>

          <p className={styles.heroSub}>
            Describe who you want to reach. The agent{' '}
            <strong>searches LinkedIn</strong>, analyzes each profile,
            finds a <strong>personalization hook</strong>, and drafts a
            message — all in under two minutes.
          </p>

          <div className={styles.heroActions}>
            <button
              className={styles.btnPrimary}
              onClick={() => router.push('/agent')}
            >
              ▶ Try the Agent
            </button>
            <button
              className={styles.btnGhost}
              onClick={() => document.getElementById('how').scrollIntoView({ behavior: 'smooth' })}
            >
              How it works ↓
            </button>
          </div>

          {/* Live stats */}
          {stats && (
            <div className={styles.statsBar}>
              <div className={styles.statItem}>
                <span className={styles.statValue}>{stats.total_profiles}</span>
                <div className={styles.statLabel}>Profiles processed</div>
              </div>
              <div className={styles.statItem}>
                <span className={styles.statValue}>{stats.avg_score}/10</span>
                <div className={styles.statLabel}>Avg relevance score</div>
              </div>
              <div className={styles.statItem}>
                <span className={styles.statValue}>{stats.high_quality_count}</span>
                <div className={styles.statLabel}>High quality (7+)</div>
              </div>
            </div>
          )}
        </div>
      </section>

      {/* ── HOW IT WORKS ── */}
      <section className={styles.section} id="how">
        <div className={styles.sectionLabel}>// how it works</div>
        <div className={styles.sectionTitle}>
          Four steps,<br />zero manual research.
        </div>

        <div className={styles.steps}>
          {[
            { num: '01', icon: '🔍', title: 'Search', desc: 'Describe your target — "ML engineers at Series A startups in India". The agent searches LinkedIn live via Tavily.' },
            { num: '02', icon: '🔬', title: 'Analyze', desc: 'Each profile is analyzed by Groq LLaMA 70B. Extracts role, company, and a specific personalization hook.' },
            { num: '03', icon: '✍️', title: 'Draft', desc: 'A personalized outreach message is drafted — under 150 words, no corporate language, specific to each person.' },
            { num: '04', icon: '📋', title: 'Export', desc: 'Results stored in ChromaDB. Exported to CSV. Never re-processes the same profile twice.' },
          ].map((step) => (
            <div key={step.num} className={styles.step}>
              <div className={styles.stepNum}>{step.num}</div>
              <span className={styles.stepIcon}>{step.icon}</span>
              <div className={styles.stepTitle}>{step.title}</div>
              <p className={styles.stepDesc}>{step.desc}</p>
            </div>
          ))}
        </div>

        {/* Terminal */}
        <div className={styles.terminal}>
          <div className={styles.terminalBar}>
            <div className={styles.termDot} style={{ background: '#ff5f56' }} />
            <div className={styles.termDot} style={{ background: '#ffbd2e' }} />
            <div className={styles.termDot} style={{ background: '#27c93f' }} />
            <span className={styles.termTitle}>pipeline.log</span>
          </div>
          <div className={styles.termBody}>
            <div><span className={styles.tPrompt}>→ </span><span className={styles.tCmd}>run_agent</span><span className={styles.tOut}>("ML engineers Series A India")</span></div>
            <div><span className={styles.tPrompt}>  </span><span className={styles.tOut}>searching Tavily...</span></div>
            <div><span className={styles.tPrompt}>  </span><span className={styles.tOk}>✓ </span><span className={styles.tOut}>found </span><span className={styles.tVal}>10</span><span className={styles.tOut}> profiles</span></div>
            <div><span className={styles.tPrompt}>  </span><span className={styles.tOut}>analyzing </span><span className={styles.tVal}>Saurabh Vij</span><span className={styles.tOut}> @ NEO...</span></div>
            <div><span className={styles.tPrompt}>  </span><span className={styles.tOk}>✓ </span><span className={styles.tOut}>score: </span><span className={styles.tVal}>9/10</span></div>
            <div><span className={styles.tPrompt}>  </span><span className={styles.tOut}>drafting message...</span></div>
            <div><span className={styles.tPrompt}>  </span><span className={styles.tOk}>✓ </span><span className={styles.tOut}>message ready (</span><span className={styles.tVal}>42 words</span><span className={styles.tOut}>)</span></div>
            <div><span className={styles.tWarn}>  ⚠ </span><span className={styles.tOut}>low score skip: James Ali (</span><span className={styles.tVal}>2/10</span><span className={styles.tOut}>)</span></div>
            <div><span className={styles.tPrompt}>  </span><span className={styles.tOk}>✓ </span><span className={styles.tOut}>complete — </span><span className={styles.tVal}>3</span><span className={styles.tOut}> profiles ready in </span><span className={styles.tVal}>19.4s</span></div>
          </div>
        </div>
      </section>

      {/* ── CTA ── */}
      <section className={styles.cta}>
        <div className={styles.ctaGlow} />
        <h2 className={styles.ctaTitle}>Ready to try it?</h2>
        <p className={styles.ctaSub}>Describe your target. Get personalized messages in under 2 minutes.</p>
        <button
          className={styles.btnPrimary}
          style={{ fontSize: '15px', padding: '16px 36px' }}
          onClick={() => router.push('/agent')}
        >
          ▶ Launch the Agent
        </button>
      </section>

    </div>
  )
}