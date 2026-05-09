import React, { useEffect, useState } from "react"
import { Badge } from "../components/ui/Badge"
import { Button } from "../components/ui/Button"
import { Card } from "../components/ui/Card"
import { Spinner } from "../components/ui/Spinner"
import { useConfig } from "../hooks/useConfig"
import type { ProviderId, ProviderSummary } from "../types"

const providerLabels: Record<ProviderId, string> = {
  gemini: "Gemini",
  codex: "Codex",
  copilot: "Copilot",
}

const PROVIDER_IDS: ProviderId[] = ["gemini", "codex", "copilot"]

interface ProviderFormState {
  enabled: boolean
  home_path: string
  passive_sync_enabled: boolean
  active_probe_enabled: boolean
}

function providerToForm(p: ProviderSummary): ProviderFormState {
  return {
    enabled: p.enabled,
    home_path: p.config.home_path,
    passive_sync_enabled: p.config.passive_sync_enabled,
    active_probe_enabled: p.config.active_probe_enabled,
  }
}

export function Settings(): React.JSX.Element {
  const { config, providers, busy, updateConfig, updateProvider, scanProvider, probeProvider } =
    useConfig()

  // Daemon interval form state
  const [probeMinutes, setProbeMinutes] = useState(60)
  const [syncMinutes, setSyncMinutes] = useState(15)
  const [daemonSaving, setDaemonSaving] = useState(false)
  const [daemonSaved, setDaemonSaved] = useState(false)

  // Provider form states
  const [providerForms, setProviderForms] = useState<Record<ProviderId, ProviderFormState>>({
    gemini: { enabled: true, home_path: "~/.gemini", passive_sync_enabled: true, active_probe_enabled: false },
    codex:  { enabled: true, home_path: "~/.codex",  passive_sync_enabled: true, active_probe_enabled: false },
    copilot: { enabled: true, home_path: "~/.copilot", passive_sync_enabled: true, active_probe_enabled: false },
  })

  const [actionBusy, setActionBusy] = useState<string | null>(null)

  // Sync form from loaded config
  useEffect(() => {
    if (config) {
      setProbeMinutes(config.daemon.active_probe_interval_minutes)
      setSyncMinutes(config.daemon.passive_sync_interval_minutes)
    }
  }, [config])

  useEffect(() => {
    if (providers.length > 0) {
      const next: Partial<Record<ProviderId, ProviderFormState>> = {}
      providers.forEach((p) => { next[p.id] = providerToForm(p) })
      setProviderForms((prev) => ({ ...prev, ...next }))
    }
  }, [providers])

  async function handleSaveDaemon(): Promise<void> {
    setDaemonSaving(true)
    try {
      await updateConfig({
        active_probe_interval_minutes: probeMinutes,
        passive_sync_interval_minutes: syncMinutes,
      })
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
      await updateProvider(id, {
        enabled: form.enabled,
        home_path: form.home_path,
        passive_sync_enabled: form.passive_sync_enabled,
        active_probe_enabled: form.active_probe_enabled,
      })
    } finally {
      setActionBusy(null)
    }
  }

  async function handleScan(id: ProviderId): Promise<void> {
    setActionBusy(`scan-${id}`)
    try {
      await scanProvider(id)
    } finally {
      setActionBusy(null)
    }
  }

  async function handleProbe(id: ProviderId): Promise<void> {
    setActionBusy(`probe-${id}`)
    try {
      await probeProvider(id)
    } finally {
      setActionBusy(null)
    }
  }

  function setProviderField<K extends keyof ProviderFormState>(
    id: ProviderId,
    field: K,
    value: ProviderFormState[K]
  ): void {
    setProviderForms((prev) => ({
      ...prev,
      [id]: { ...prev[id], [field]: value },
    }))
  }

  if (!config && !busy) {
    return (
      <div className="flex flex-col gap-6 p-6">
        <div className="rounded-lg border border-red-700/40 bg-red-900/20 px-4 py-3 text-sm text-red-400">
          Failed to load configuration. Make sure the daemon is running.
        </div>
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-6 p-6 min-h-0 overflow-y-auto">
      <div>
        <h1 className="text-xl font-semibold text-slate-100">Settings</h1>
        <p className="text-sm text-slate-400 mt-0.5">Daemon and provider configuration</p>
      </div>

      {/* Daemon settings */}
      <Card>
        <h2 className="text-sm font-semibold text-slate-300 mb-4">Daemon Settings</h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 max-w-lg">
          <label className="flex flex-col gap-1.5">
            <span className="text-xs text-slate-400">Active probe interval (minutes)</span>
            <input
              type="number"
              min={1}
              value={probeMinutes}
              onChange={(e) => setProbeMinutes(Number(e.target.value))}
              className="rounded-lg border border-slate-600 bg-slate-900 px-3 py-2 text-sm text-slate-100
                focus:outline-none focus:ring-2 focus:ring-violet-500 focus:border-transparent"
            />
          </label>
          <label className="flex flex-col gap-1.5">
            <span className="text-xs text-slate-400">Passive sync interval (minutes)</span>
            <input
              type="number"
              min={1}
              value={syncMinutes}
              onChange={(e) => setSyncMinutes(Number(e.target.value))}
              className="rounded-lg border border-slate-600 bg-slate-900 px-3 py-2 text-sm text-slate-100
                focus:outline-none focus:ring-2 focus:ring-violet-500 focus:border-transparent"
            />
          </label>
        </div>
        <div className="mt-4 flex items-center gap-3">
          <Button variant="primary" size="sm" loading={daemonSaving} onClick={handleSaveDaemon}>
            Save
          </Button>
          {daemonSaved && <span className="text-xs text-green-400">Saved!</span>}
        </div>
        {config && (
          <div className="mt-4 pt-4 border-t border-slate-700 grid grid-cols-2 sm:grid-cols-3 gap-3 text-xs text-slate-500">
            <span>Host: <span className="text-slate-400">{config.daemon.web_host}:{config.daemon.web_port}</span></span>
            <span>DB: <code className="text-slate-400">{config.daemon.database_path}</code></span>
            <span>Log level: <span className="text-slate-400">{config.daemon.log_level}</span></span>
          </div>
        )}
      </Card>

      {/* Provider sections */}
      {PROVIDER_IDS.map((id) => {
        const form = providerForms[id]
        const isBusy = actionBusy !== null || busy
        return (
          <Card key={id}>
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-sm font-semibold text-slate-300">{providerLabels[id]}</h2>
              <Badge variant={form.enabled ? "success" : "default"}>
                {form.enabled ? "Enabled" : "Disabled"}
              </Badge>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 max-w-lg mb-4">
              <label className="flex flex-col gap-1.5">
                <span className="text-xs text-slate-400">Home path</span>
                <input
                  type="text"
                  value={form.home_path}
                  onChange={(e) => setProviderField(id, "home_path", e.target.value)}
                  className="rounded-lg border border-slate-600 bg-slate-900 px-3 py-2 text-sm text-slate-100
                    focus:outline-none focus:ring-2 focus:ring-violet-500 focus:border-transparent"
                />
              </label>
            </div>

            <div className="flex flex-wrap gap-4 mb-4">
              <Toggle
                label="Enabled"
                checked={form.enabled}
                onChange={(v) => setProviderField(id, "enabled", v)}
              />
              <Toggle
                label="Passive sync"
                checked={form.passive_sync_enabled}
                onChange={(v) => setProviderField(id, "passive_sync_enabled", v)}
              />
              <Toggle
                label="Active probe"
                checked={form.active_probe_enabled}
                onChange={(v) => setProviderField(id, "active_probe_enabled", v)}
              />
            </div>

            {form.active_probe_enabled && (
              <p className="text-xs text-amber-400 mb-4">
                Active probes may consume provider quota.
              </p>
            )}

            <div className="flex flex-wrap gap-2">
              <Button
                variant="primary"
                size="sm"
                loading={actionBusy === `save-${id}`}
                disabled={isBusy && actionBusy !== `save-${id}`}
                onClick={() => handleSaveProvider(id)}
              >
                Save
              </Button>
              <Button
                variant="ghost"
                size="sm"
                loading={actionBusy === `scan-${id}`}
                disabled={isBusy && actionBusy !== `scan-${id}`}
                onClick={() => handleScan(id)}
              >
                Scan
              </Button>
              <Button
                variant="ghost"
                size="sm"
                loading={actionBusy === `probe-${id}`}
                disabled={isBusy && actionBusy !== `probe-${id}`}
                onClick={() => handleProbe(id)}
              >
                Probe
              </Button>
            </div>
          </Card>
        )
      })}
    </div>
  )
}

interface ToggleProps {
  label: string
  checked: boolean
  onChange: (value: boolean) => void
}

function Toggle({ label, checked, onChange }: ToggleProps): React.JSX.Element {
  return (
    <label className="flex items-center gap-2 cursor-pointer select-none">
      <div
        role="switch"
        aria-checked={checked}
        onClick={() => onChange(!checked)}
        className={`relative inline-flex h-5 w-9 rounded-full transition-colors cursor-pointer
          ${checked ? "bg-violet-600" : "bg-slate-600"}`}
      >
        <span
          className={`inline-block h-4 w-4 mt-0.5 rounded-full bg-white shadow transition-transform
            ${checked ? "translate-x-4" : "translate-x-0.5"}`}
        />
      </div>
      <span className="text-sm text-slate-300">{label}</span>
    </label>
  )
}
