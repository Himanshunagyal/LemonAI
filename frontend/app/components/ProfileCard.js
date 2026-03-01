'use client'

import { useState } from 'react'
import styles from './ProfileCard.module.css'

export default function ProfileCard({ profile, index }) {
  const [copiedMsg, setCopiedMsg] = useState(false)
  const [copiedUrl, setCopiedUrl] = useState(false)

  const scoreColor =
    profile.score >= 8 ? 'var(--accent)' :
    profile.score >= 6 ? 'var(--accent2)' :
    'var(--warn)'

  function copyText(text, setCopied) {
    navigator.clipboard.writeText(text).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    })
  }

  return (
    <div
      className={styles.card}
      style={{ animationDelay: `${index * 0.08}s` }}
    >
      {/* HEADER */}
      <div className={styles.header}>
        <div className={styles.identity}>
          <div className={styles.name}>{profile.name}</div>
          <div className={styles.role}>
            {profile.role !== 'Not found' && profile.role}
            {profile.role !== 'Not found' && profile.company !== 'Not found' && ' @ '}
            {profile.company !== 'Not found' && profile.company}
            {profile.url && (
              <>
                {' · '}
                <a
                  href={profile.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className={styles.profileLink}
                >
                  View Profile ↗
                </a>
              </>
            )}
          </div>
        </div>
        <div className={styles.scoreBadge}>
          <div className={styles.scoreNum} style={{ color: scoreColor }}>
            {profile.score}
          </div>
          <div className={styles.scoreLabel}>/ 10</div>
        </div>
      </div>

      {/* BODY */}
      <div className={styles.body}>
        <div>
          <div className={styles.fieldLabel}>Personalization Hook</div>
          <div className={styles.hook}>{profile.hook}</div>
        </div>
        <div>
          <div className={styles.fieldLabel}>Outreach Message</div>
          <div className={styles.message}>{profile.message}</div>
        </div>
      </div>

      {/* FOOTER */}
      <div className={styles.footer}>
        <button
          className={`${styles.copyBtn} ${copiedMsg ? styles.copied : ''}`}
          onClick={() => copyText(profile.message, setCopiedMsg)}
        >
          {copiedMsg ? '✓ Copied!' : '⧉ Copy Message'}
        </button>
        <button
          className={`${styles.copyBtn} ${copiedUrl ? styles.copied : ''}`}
          onClick={() => copyText(profile.url, setCopiedUrl)}
        >
          {copiedUrl ? '✓ Copied!' : '⧉ Copy URL'}
        </button>
        <div className={`${styles.statusPill} ${styles[profile.status]}`}>
          {profile.status}
        </div>
      </div>
    </div>
  )
}