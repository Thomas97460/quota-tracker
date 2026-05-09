import React, { useEffect, useState } from "react"
import { useConfig } from "../hooks/useConfig"
import type { ProviderId, ProviderSummary } from "../types"

const providerLabels: Record<ProviderId, string> = {
  gemini: "Gemini",
  codex: "Codex",
  copilot: "Copilot",
  claude: "Claude",
}

const PROVIDER_IDS: ProviderId[] = ["gemini", "codex", "copilot", "claude"]

const PROVIDER_COLOR_VARS: Record<ProviderId, string> = {
  gemini: "var(--gemini)",
  codex: "var(--codex)",
  copilot: "var(--copilot)",
  claude: "var(--claude)",
}

interface ProviderFormState {
  enabled: boolean
  home_path: string
}

function providerToForm(p: ProviderSummary): ProviderFormState {
  return {
    enabled: p.enabled,
    home_path: p.config.home_path,
  }
}

export function Settings(): React.JSX.Element {
  const { config, providers, busy, updateConfig, updateProvider, scanProvider } = useConfig()

  const [syncMinutes, setSyncMinutes] = useState(5)
  const [daemonSaving, setDaemonSaving] = useState(false)
  const [daemonSaved, setDaemonSaved] = useState(false)

  const [providerForms, setProviderForms] = useState<Record<ProviderId, ProviderFormState>>({
    gemini: { enabled: true, home_path: "~/.gemini" },
    codex: { enabled: true, home_path: "~/.codex" },
    copilot: { enabled: true, home_path: "~/.copilot" },
    claude: { enabled: true, home_path: "~/.claude" },
  })

  const [actionBusy, setActionBusy] = useState<string | null>(null)

  useEffect(() => {
    if (config) {
      setSyncMinutes(
        config.daemon.sync_interval_minutes ??
          config.daemon.passive_sync_interval_minutes ??
          5,
      )
    }
  }, [config])

  useEffect(() => {
    if (providers.length > 0) {
      const next: Partial<Record<ProviderId, ProviderFormState>> = {}
      providers.forEach((p) => {
        next[p.id] = providerToForm(p)
      })
      setProviderForms((prev) => ({ ...prev, ...next }))
    }
  }, [providers])

  async function handleSaveDaemon(): Promise<void> {
    setDaemonSaving(true)
    try {
      await updateConfig({ sync_interval_minutes: syncMinutes })
      setDaemonSaved(true)
      setTimeout(() => setDaemonSaved(false), 2000)
    } finally {
      setDaemonSaving(false)
    }
  }

  async function handleSaveProvider(id: ProviderId): Promise<void> {
    const form = providerForms[id]
    setActionBusy(`save-${id}`)
    try {
      await updateProvider(id, { enabled: form.enabled, home_path: form.home_path })
    } finally {
      setActionBusy(null)
    }
  }

  async function handleSync(id: ProviderId): Promise<void> {
    setActionBusy(`sync-${id}`)
    try {
      await scanProvider(id)
    } finally {
      setActionBusy(null)
    }
  }

  function setProviderField<K extends keyof ProviderFormState>(
    id: ProviderId,
    field: K,
    value: ProviderFormState[K],
  ): void {
    setProviderForms((prev) => ({
      ...prev,
      [id]: { ...prev[id], [field]: value },
    }))
  }

  if (!config && !busy) {
    return (
      <div style={{ padding: "22px 28px" }}>
        <div
          style={{
            background: "color-mix(in oklab, var(--crit) 12%, transparent)",
            border: "1px solid color-mix(in oklab, var(--crit) 28%, transparent)",
            borderRadius: "var(--radius-2)",
            padding: "12px 16px",
            fontSize: 13,
            color: "var(--crit)",
          }}
        >
          Failed to load configuration. Make sure the daemon is running.
        </div>
      </div>
    )
  }

  const inputStyle: React.CSSProperties = {
    background: "var(--bg-2)",
    border: "1px solid var(--border-1)",
    borderRadius: "var(--radius-1)",
    padding: "8px 12px",
    fontSize: 13,
    color: "var(--fg-1)",
    fontFamily: "inherit",
    width: "100%",
    outline: "none",
  }

  return (
    <>
      <div className="topbar">
        <div className="topbar-crumb">
          <span className="crumb-title">Settings</span>
        </div>
      </div>

      <div className="page">
        <div className="page-head">
          <div>
            <div className="page-title">Settings</div>
            <div className="page-sub">Daemon and provider configuration</div>
          </div>
        </div>

        {/* Daemon settings card */}
        <div className="card">
          <div className="card-head">
            <span className="card-title">Daemon Settings</span>
          </div>
          <div className="card-body">
            <div style={{ maxWidth: 320 }}>
              <label style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                <span style={{ fontSize: 12, color: "var(--fg-3)" }}>
                  Sync interval (minutes)
                </span>
                <input
                  type="number"
                  min={1}
                  value={syncMinutes}
                  onChange={(e) => setSyncMinutes(Number(e.target.value))}
                  style={inputStyle}
                />
              </label>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 12, marginTop: 16 }}>
              <button
                className="icon-btn primary"
                disabled={daemonSaving}
                onClick={handleSaveDaemon}
              >
                {daemonSaving ? "Saving…" : "Save"}
              </button>
              {daemonSaved && (
                <span style={{ fontSize: 12, color: "var(--ok)" }}>Saved!</span>
              )}
            </div>
            {config && (
              <div
                style={{
                  marginTop: 16,
                  paddingTop: 16,
                  borderTop: "1px solid var(--border-1)",
                  display: "grid",
                  gridTemplateColumns: "1fr 1fr 1fr",
                  gap: 12,
                  fontSize: 12,
                  color: "var(--fg-3)",
                }}
              >
                <span>
                  Host:{" "}
                  <span style={{ color: "var(--fg-2)" }}>
                    {config.daemon.web_host}:{config.daemon.web_port}
                  </span>
                </span>
                <span>
                  DB:{" "}
                  <code style={{ fontFamily: "var(--font-mono)", color: "var(--fg-2)" }}>
                    {config.daemon.database_path}
                  </code>
                </span>
                <span>
                  Log level:{" "}
                  <span style={{ color: "var(--fg-2)" }}>{config.daemon.log_level}</span>
                </span>
              </div>
            )}
          </div>
        </div>

        {/* Provider cards */}
        {PROVIDER_IDS.map((id) => {
          const form = providerForms[id]
          const isBusy = actionBusy !== null || busy
          const color = PROVIDER_COLOR_VARS[id]

          return (
            <div key={id} className="card">
              <div className="card-head">
                <span className="card-title" style={{ color }}>
                  {providerLabels[id]}
                </span>
                <div className="card-actions">
                  <span
                    className={`tag${form.enabled ? " ok" : ""}`}
                  >
                    {form.enabled ? "Enabled" : "Disabled"}
                  </span>
                </div>
              </div>
              <div className="card-body">
                <div
                  style={{
                    display: "grid",
                    gridTemplateColumns: "1fr 1fr",
                    gap: 16,
                    maxWidth: 520,
                    marginBottom: 16,
                  }}
                >
                  <label style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                    <span style={{ fontSize: 12, color: "var(--fg-3)" }}>Home path</span>
                    <input
                      type="text"
                      value={form.home_path}
                      onChange={(e) => setProviderField(id, "home_path", e.target.value)}
                      style={inputStyle}
                    />
                  </label>
                </div>

                <div style={{ marginBottom: 16 }}>
                  <Toggle
                    label="Enabled"
                    checked={form.enabled}
                    onChange={(v) => setProviderField(id, "enabled", v)}
                  />
                </div>

                <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                  <button
                    className="icon-btn primary"
                    disabled={isBusy && actionBusy !== `save-${id}`}
                    onClick={() => handleSaveProvider(id)}
                  >
                    {actionBusy === `save-${id}` ? "Saving…" : "Save"}
                  </button>
                  <button
                    className="icon-btn"
                    disabled={isBusy && actionBusy !== `sync-${id}`}
                    onClick={() => handleSync(id)}
                  >
                    {actionBusy === `sync-${id}` ? "Syncing…" : "Sync now"}
                  </button>
                </div>
              </div>
            </div>
          )
        })}
      </div>
    </>
  )
}

interface ToggleProps {
  label: string
  checked: boolean
  onChange: (value: boolean) => void
}

function Toggle({ label, checked, onChange }: ToggleProps): React.JSX.Element {
  return (
    <label
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 8,
        cursor: "pointer",
        userSelect: "none",
      }}
    >
      <div
        role="switch"
        aria-checked={checked}
        onClick={() => onChange(!checked)}
        style={{
          position: "relative",
          display: "inline-flex",
          width: 36,
          height: 20,
          borderRadius: 99,
          background: checked ? "var(--accent)" : "var(--border-2)",
          cursor: "pointer",
          transition: "background 120ms",
          flexShrink: 0,
        }}
      >
        <span
          style={{
            position: "absolute",
            top: 2,
            left: checked ? 18 : 2,
            width: 16,
            height: 16,
            borderRadius: 99,
            background: "white",
            transition: "left 120ms",
            boxShadow: "0 1px 3px rgba(0,0,0,0.3)",
          }}
        />
      </div>
      <span style={{ fontSize: 13, color: "var(--fg-2)" }}>{label}</span>
    </label>
  )
}
