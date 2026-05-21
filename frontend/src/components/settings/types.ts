import type { SettingsConfig } from "../../lib/types";

export type UpdateSettingsDraft = (updater: (current: SettingsConfig) => SettingsConfig) => void;
export type VlmEndpointKey = "local" | "remote" | "frontier";
export type GlmEndpointKey = "local" | "remote";
export type AgentInheritRoute = "active" | VlmEndpointKey;

export const VLM_ENDPOINTS: VlmEndpointKey[] = ["local", "remote", "frontier"];
export const GLM_ENDPOINTS: GlmEndpointKey[] = ["local", "remote"];
export const AGENT_INHERIT_ROUTES: AgentInheritRoute[] = ["active", ...VLM_ENDPOINTS];
