import { useCallback, useEffect, useState } from "react"

interface VersionInfo {
  current: string
  latest: string | null
  update_available: boolean
  install_method: string
}

interface UseVersionResult {
  current: string
  updateAvailable: boolean
  latestVersion: string | null
  installMethod: string
}

export function useVersion(): UseVersionResult {
  const [info, setInfo] = useState<VersionInfo>({ current: "", latest: null, update_available: false, install_method: "curl" })

  const fetchVersion = useCallback(async () => {
    try {
      const r = await fetch("/api/version")
      if (r.ok) setInfo(await r.json())
    } catch {
      // ignore — offline or dev mode
    }
  }, [])

  useEffect(() => {
    fetchVersion()
    const id = setInterval(fetchVersion, 30 * 60 * 1000)
    return () => clearInterval(id)
  }, [fetchVersion])

  return {
    current: info.current,
    updateAvailable: info.update_available,
    latestVersion: info.latest,
    installMethod: info.install_method ?? "curl",
  }
}
