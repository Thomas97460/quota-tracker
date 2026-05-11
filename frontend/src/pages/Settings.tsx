import React, { useEffect, useState } from "react"
import { ThemeToggle } from "../components/ui/ThemeToggle"
import { useConfig } from "../hooks/useConfig"
import type { ModelPricing, ProviderId, ProviderSummary } from "../types"

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

  const [pricing, setPricing] = useState<Record<string, ModelPricing>>({})
  const [pricingSearch, setPricingSearch] = useState("")
  const [pricingSaving, setPricingSaving] = useState(false)
  const [pricingSaved, setPricingSaved] = useState(false)

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
      setPricing(config.pricing || {})
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

  async function handleSavePricing(): Promise<void> {
    setPricingSaving(true)
    try {
      await updateConfig({ pricing })
      setPricingSaved(true)
      setTimeout(() => setPricingSaved(false), 2000)
    } finally {
      setPricingSaving(false)
    }
  }

  function updatePricingField(key: string, field: keyof ModelPricing, value: string): void {
    const num = parseFloat(value) || 0
    setPricing((prev) => ({
      ...prev,
      [key]: { ...prev[key], [field]: num },
    }))
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
        <div className="topbar-spacer" />
        <ThemeToggle />
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

        {/* Pricing card */}
        <div className="card">
          <div className="card-head">
            <span className="card-title">Model Pricing</span>
            <div className="card-actions">
              <input
                type="text"
                placeholder="Filter models..."
                className="select"
                style={{ width: 180, height: 28, padding: "0 8px" }}
                value={pricingSearch}
                onChange={(e) => setPricingSearch(e.target.value)}
              />
            </div>
          </div>
          <div className="card-body" style={{ padding: 0 }}>
            <div style={{ maxHeight: 400, overflowY: "auto" }}>
              <table className="table" style={{ borderTop: "none" }}>
                <thead>
                  <tr style={{ position: "sticky", top: 0, background: "var(--bg-1)", zIndex: 10 }}>
                    <th>Model Key</th>
                    <th className="num">Input ($/1M)</th>
                    <th className="num">Cached ($/1M)</th>
                    <th className="num">Output ($/1M)</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(pricing)
                    .filter(([k]) => k.toLowerCase().includes(pricingSearch.toLowerCase()))
                    .sort(([a], [b]) => a.localeCompare(b))
                    .map(([key, p]) => (
                      <tr key={key}>
                        <td className="mono" style={{ fontSize: 11 }}>{key}</td>
                        <td className="num">
                          <input
                            type="number"
                            step="0.0001"
                            value={p.input_1m}
                            onChange={(e) => updatePricingField(key, "input_1m", e.target.value)}
                            style={{ ...inputStyle, width: 75, textAlign: "right", padding: "4px 6px" }}
                          />
                        </td>
                        <td className="num">
                          <input
                            type="number"
                            step="0.0001"
                            value={p.cached_1m}
                            onChange={(e) => updatePricingField(key, "cached_1m", e.target.value)}
                            style={{ ...inputStyle, width: 75, textAlign: "right", padding: "4px 6px" }}
                          />
                        </td>
                        <td className="num">
                          <input
                            type="number"
                            step="0.0001"
                            value={p.output_1m}
                            onChange={(e) => updatePricingField(key, "output_1m", e.target.value)}
                            style={{ ...inputStyle, width: 75, textAlign: "right", padding: "4px 6px" }}
                          />
                        </td>
                      </tr>
                    ))}
                </tbody>
              </table>
            </div>
            <div style={{ padding: 16, borderTop: "1px solid var(--border-1)", display: "flex", alignItems: "center", gap: 12 }}>
              <button
                className="icon-btn primary"
                disabled={pricingSaving}
                onClick={handleSavePricing}
              >
                {pricingSaving ? "Saving…" : "Save Pricing"}
              </button>
              {pricingSaved && (
                <span style={{ fontSize: 12, color: "var(--ok)" }}>Saved!</span>
              )}
              <span className="dim" style={{ fontSize: 11, marginLeft: "auto" }}>
                Key format: <code>provider_id:model_name</code>
              </span>
            </div>
          </div>
        </div>

        {/* Provider cards */}
        <div className="grid-2eq">
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
                      gridTemplateColumns: "1fr",
                      gap: 16,
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

                  <div style={{ marginBottom: 16, display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                    <Toggle
                      label="Enabled"
                      checked={form.enabled}
                      onChange={(v) => setProviderField(id, "enabled", v)}
                    />
                    <div style={{ display: "flex", gap: 8 }}>
                      <button
                        className="icon-btn"
                        disabled={isBusy && actionBusy !== `sync-${id}`}
                        onClick={() => handleSync(id)}
                        style={{ padding: "4px 8px", fontSize: 12 }}
                      >
                        {actionBusy === `sync-${id}` ? "Syncing…" : "Sync"}
                      </button>
                      <button
                        className="icon-btn primary"
                        disabled={isBusy && actionBusy !== `save-${id}`}
                        onClick={() => handleSaveProvider(id)}
                        style={{ padding: "4px 8px", fontSize: 12 }}
                      >
                        {actionBusy === `save-${id}` ? "Saving…" : "Save"}
                      </button>
                    </div>
                  </div>
                </div>
              </div>
            )
          })}
        </div>
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
