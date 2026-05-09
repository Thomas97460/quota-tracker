import { createContext, useContext } from "react"
import type { ProviderSummary } from "../types"

interface ProvidersContextValue {
  providers: ProviderSummary[]
}

export const ProvidersContext = createContext<ProvidersContextValue>({ providers: [] })

export function useProviders(): ProvidersContextValue {
  return useContext(ProvidersContext)
}
