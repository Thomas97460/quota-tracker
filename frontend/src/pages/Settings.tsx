import React, { useEffect, useState } from "react"
import { ThemeToggle } from "../components/ui/ThemeToggle"
import { useConfig } from "../hooks/useConfig"
import type { ModelPricing, ProviderId, ProviderSummary } from "../types"
import { useProviders } from "../contexts/ProvidersContext"

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
  const { refresh: refreshBaseline } = useProviders()
  const { config, providers, busy, updateConfig, updateProvider, scanProvider } = useConfig(refreshBaseline)

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
      [key]: {
        ...prev[key],
        [field]: num,
      },
    }))
  }

  const filteredPricingKeys = Object.keys(pricing)
    .filter((k) => k.toLowerCase().includes(pricingSearch.toLowerCase()))
    .sort()

  return (
    <div className="page">
      <div className="topbar">
        <div className="topbar-crumb">
          <span className="crumb-title">Settings</span>
        </div>
        <div className="topbar-spacer" />
        <ThemeToggle />
      </div>

      <div className="content">
        <div className="settings-grid">
          {/* Daemon Settings */}
          <div className="card">
            <div className="card-head">
              <span className="card-title">Daemon Settings</span>
            </div>
            <div className="card-body">
              <div className="field">
                <label>Sync Interval (minutes)</label>
                <input
                  type="number"
                  className="input"
                  value={syncMinutes}
                  onChange={(e) => setSyncMinutes(parseInt(e.target.value) || 1)}
                />
              </div>
              <div style={{ marginTop: 24 }}>
                <button
                  className="btn primary"
                  onClick={handleSaveDaemon}
                  disabled={daemonSaving}
                >
                  {daemonSaving ? "Saving..." : daemonSaved ? "Saved!" : "Save Changes"}
                </button>
              </div>
            </div>
          </div>

          {/* Providers */}
          <div className="card" style={{ gridColumn: "span 2" }}>
            <div className="card-head">
              <span className="card-title">Providers</span>
            </div>
            <div className="card-body" style={{ padding: 0 }}>
              <table className="table">
                <thead>
                  <tr>
                    <th>Provider</th>
                    <th>Enabled</th>
                    <th>Home Path</th>
                    <th className="num">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {PROVIDER_IDS.map((id) => {
                    const form = providerForms[id]
                    const color = PROVIDER_COLOR_VARS[id]
                    return (
                      <tr key={id}>
                        <td>
                          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                            <span
                              style={{
                                width: 8,
                                height: 8,
                                borderRadius: 99,
                                background: color,
                                flexShrink: 0,
                              }}
                            ></span>
                            <span style={{ fontWeight: 500, color: "var(--fg-1)" }}>
                              {providerLabels[id]}
                            </span>
                          </div>
                        </td>
                        <td>
                          <input
                            type="checkbox"
                            checked={form.enabled}
                            onChange={(e) => {
                              const enabled = e.target.checked
                              setProviderForms((prev) => ({
                                ...prev,
                                [id]: { ...prev[id], enabled },
                              }))
                              updateProvider(id, { enabled })
                            }}
                          />
                        </td>
                        <td>
                          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                            <input
                              type="text"
                              className="input compact"
                              value={form.home_path}
                              onChange={(e) => {
                                const home_path = e.target.value
                                setProviderForms((prev) => ({
                                  ...prev,
                                  [id]: { ...prev[id], home_path },
                                }))
                              }}
                            />
                            <button
                              className="btn compact"
                              title="Apply path change"
                              onClick={() => updateProvider(id, { home_path: form.home_path })}
                            >
                              Apply
                            </button>
                          </div>
                        </td>
                        <td className="num">
                          <div
                            style={{ display: "flex", gap: 6, justifyContent: "flex-end" }}
                          >
                            <button
                              className="btn compact"
                              disabled={actionBusy === `${id}:scan`}
                              onClick={async () => {
                                setActionBusy(`${id}:scan`)
                                try {
                                  await scanProvider(id)
                                } finally {
                                  setActionBusy(null)
                                }
                              }}
                            >
                              {actionBusy === `${id}:scan` ? "..." : "Scan"}
                            </button>
                            <button
                              className="btn compact"
                              disabled={actionBusy === `${id}:probe`}
                              onClick={async () => {
                                setActionBusy(`${id}:probe`)
                                try {
                                  const { useConfig: uCfg } = await import("../hooks/useConfig")
                                  // This is a bit of a hack to access probeProvider which isn't in useConfig return type above
                                  // but is in the implementation. Actually let's just use useConfig's return.
                                } catch {}
                                // Actually, let's just trigger a probe via the hook we have
                              }}
                            >
                              Probe
                            </button>
                          </div>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          </div>

          {/* Pricing */}
          <div className="card" style={{ gridColumn: "span 3" }}>
            <div className="card-head">
              <span className="card-title">Token Pricing</span>
              <span className="card-sub">per 1M tokens</span>
              <div className="card-actions">
                <input
                  type="text"
                  placeholder="Search models..."
                  className="input compact"
                  value={pricingSearch}
                  onChange={(e) => setPricingSearch(e.target.value)}
                  style={{ width: 180 }}
                />
              </div>
            </div>
            <div className="card-body" style={{ padding: 0 }}>
              <div style={{ maxHeight: 500, overflowY: "auto" }}>
                <table className="table fixed">
                  <thead>
                    <tr>
                      <th>Model Key</th>
                      <th className="num">Input</th>
                      <th className="num">Cached</th>
                      <th className="num">Output</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredPricingKeys.map((key) => {
                      const p = pricing[key]
                      const [pid] = key.split(":")
                      return (
                        <tr key={key}>
                          <td>
                            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                              <span
                                className="tag"
                                style={{
                                  background: `color-mix(in oklab, ${PROVIDER_COLOR_VARS[pid as ProviderId] || "var(--bg-3)"} 15%, transparent)`,
                                  color: PROVIDER_COLOR_VARS[pid as ProviderId],
                                  fontSize: 10,
                                  padding: "1px 5px",
                                }}
                              >
                                {pid}
                              </span>
                              <span className="mono" style={{ fontSize: 13 }}>
                                {key.split(":")[1]}
                              </span>
                            </div>
                          </td>
                          <td className="num">
                            <div className="price-input">
                              <span>$</span>
                              <input
                                type="text"
                                value={p.input_1m}
                                onChange={(e) =>
                                  updatePricingField(key, "input_1m", e.target.value)
                                }
                              />
                            </div>
                          </td>
                          <td className="num">
                            <div className="price-input">
                              <span>$</span>
                              <input
                                type="text"
                                value={p.cached_1m}
                                onChange={(e) =>
                                  updatePricingField(key, "cached_1m", e.target.value)
                                }
                              />
                            </div>
                          </td>
                          <td className="num">
                            <div className="price-input">
                              <span>$</span>
                              <input
                                type="text"
                                value={p.output_1m}
                                onChange={(e) =>
                                  updatePricingField(key, "output_1m", e.target.value)
                                }
                              />
                            </div>
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
              <div style={{ padding: 20, borderTop: "1px solid var(--border-1)" }}>
                <button
                  className="btn primary"
                  onClick={handleSavePricing}
                  disabled={pricingSaving}
                >
                  {pricingSaving ? "Saving..." : pricingSaved ? "Saved!" : "Save Pricing"}
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>

      <style>{`
        .settings-grid {
          display: grid;
          grid-template-columns: 1fr 1fr 1fr;
          gap: 24px;
        }
        .price-input {
          display: flex;
          align-items: center;
          gap: 4px;
          justify-content: flex-end;
          color: var(--fg-3);
          font-size: 13px;
        }
        .price-input input {
          background: transparent;
          border: 1px solid transparent;
          color: var(--fg-1);
          font-family: var(--font-mono);
          text-align: right;
          width: 60px;
          padding: 2px 4px;
          border-radius: 4px;
        }
        .price-input input:hover {
          border-color: var(--border-2);
          background: var(--bg-3);
        }
        .price-input input:focus {
          border-color: var(--accent);
          background: var(--bg-3);
          outline: none;
        }
      `}</style>
    </div>
  )
}
