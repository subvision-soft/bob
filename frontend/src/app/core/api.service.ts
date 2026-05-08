/**
 * API Service — Typed HTTP client for all Subvision Studio REST endpoints.
 */

import { Injectable } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';

const API_BASE = 'http://localhost:8000/api';

export interface Camera {
  id: string;
  name: string;
  label: string;
  source_type: string;
  source_url: string | null;
  obs_scene_name: string | null;
  enabled: boolean;
  is_active: boolean;
  subscriptions: CameraSubscription[];
}

export interface CameraObsSceneOption {
  scene_name: string;
  weight: number;
}

export interface CameraSubscription {
  event_type: string;
  mode: 'INFORM_ONLY' | 'PREPARE' | 'SWITCH_IF_HIGH_SCORE' | 'FORCE_SWITCH';
  priority: number;
  duration_ms: number;
  cooldown_ms: number;
  delay_ms: number;
  enabled: boolean;
  conditions?: Record<string, unknown>;
  obs_scene_options: CameraObsSceneOption[];
}

export interface CameraContext {
  camera_id: string;
  last_event_type: string | null;
  last_event_severity: string | null;
  interest_score: number;
  is_on_air: boolean;
  is_in_cooldown: boolean;
  cooldown_remaining_ms: number;
  pending_transition: boolean;
  pending_mode: string | null;
  time_since_last_activity_s: number;
  time_since_last_on_air_s: number;
  switch_count: number;
  recent_events: string[];
}

export interface RuleProfile {
  id: string;
  name: string;
  description: string | null;
  is_active: boolean;
  parent_profile_id: string | null;
  config: Record<string, unknown> | null;
}

export interface EventLogEntry {
  id: string;
  event_type: string;
  severity: string;
  competition_id: string | null;
  athlete_id: string | null;
  lane: number | null;
  frame_id: number | null;
  received_at: number;
}

export interface OBSStatus {
  state: string;
  url: string;
  current_program: string | null;
  current_preview: string | null;
  scenes: string[];
}

export interface HealthStatus {
  status: string;
  version: string;
  uptime_s: number;
  ws_connections: number;
  cameras_registered: number;
}

@Injectable({ providedIn: 'root' })
export class ApiService {
  constructor(private http: HttpClient) { }

  // ── Cameras ──────────────────────────────────────────────────────
  getCameras(): Observable<Camera[]> {
    return this.http.get<Camera[]>(`${API_BASE}/cameras`);
  }
  createCamera(camera: Partial<Camera>): Observable<Camera> {
    return this.http.post<Camera>(`${API_BASE}/cameras`, camera);
  }
  updateCamera(id: string, camera: Partial<Camera>): Observable<Camera> {
    return this.http.put<Camera>(`${API_BASE}/cameras/${id}`, camera);
  }
  deleteCamera(id: string): Observable<void> {
    return this.http.delete<void>(`${API_BASE}/cameras/${id}`);
  }
  getCameraContext(id: string): Observable<CameraContext> {
    return this.http.get<CameraContext>(`${API_BASE}/cameras/${id}/context`);
  }
  getAllScores(): Observable<CameraContext[]> {
    return this.http.get<CameraContext[]>(`${API_BASE}/cameras/live/scores`);
  }
  simulateCameraEvent(cameraId: string, eventType: string, extra?: Record<string, unknown>): Observable<unknown> {
    return this.http.post(`${API_BASE}/cameras/${cameraId}/simulate`, {
      event_type: eventType,
      ...extra,
    });
  }

  // ── Rules ────────────────────────────────────────────────────────
  getProfiles(): Observable<RuleProfile[]> {
    return this.http.get<RuleProfile[]>(`${API_BASE}/rules/profiles`);
  }
  createProfile(profile: Partial<RuleProfile>): Observable<RuleProfile> {
    return this.http.post<RuleProfile>(`${API_BASE}/rules/profiles`, profile);
  }
  activateProfile(id: string): Observable<unknown> {
    return this.http.post(`${API_BASE}/rules/profiles/${id}/activate`, {});
  }
  deleteProfile(id: string): Observable<void> {
    return this.http.delete<void>(`${API_BASE}/rules/profiles/${id}`);
  }

  // ── Events ───────────────────────────────────────────────────────
  getEvents(limit = 100): Observable<EventLogEntry[]> {
    return this.http.get<EventLogEntry[]>(`${API_BASE}/events`, {
      params: new HttpParams().set('limit', limit),
    });
  }
  getEventTypes(): Observable<{ type: string; severity: string }[]> {
    return this.http.get<{ type: string; severity: string }[]>(`${API_BASE}/events/types`);
  }
  simulateEvent(eventType: string, extra?: Record<string, unknown>): Observable<unknown> {
    return this.http.post(`${API_BASE}/events/simulate`, {
      event_type: eventType,
      ...extra,
    });
  }

  // ── OBS ──────────────────────────────────────────────────────────
  getObsStatus(): Observable<OBSStatus> {
    return this.http.get<OBSStatus>(`${API_BASE}/obs/status`);
  }
  connectObs(url: string, password: string): Observable<unknown> {
    return this.http.post(`${API_BASE}/obs/connect`, { url, password });
  }
  disconnectObs(): Observable<unknown> {
    return this.http.post(`${API_BASE}/obs/disconnect`, {});
  }
  setObsScene(sceneName: string, target: 'program' | 'preview' = 'program'): Observable<unknown> {
    return this.http.post(`${API_BASE}/obs/scene`, { scene_name: sceneName, target });
  }
  getObsScenes(): Observable<string[]> {
    return this.http.get<string[]>(`${API_BASE}/obs/scenes`);
  }

  // ── Monitoring ───────────────────────────────────────────────────
  getHealth(): Observable<HealthStatus> {
    return this.http.get<HealthStatus>(`${API_BASE}/monitoring/health`);
  }
  getSwitchHistory(limit = 20): Observable<unknown[]> {
    return this.http.get<unknown[]>(`${API_BASE}/monitoring/switch-history`, {
      params: new HttpParams().set('limit', limit),
    });
  }

  // ── Settings ──────────────────────────────────────────────────────
  getSettings(): Observable<{ status: string; settings: Record<string, unknown> }> {
    return this.http.get<{ status: string; settings: Record<string, unknown> }>(`${API_BASE}/settings`);
  }
  
  updateSetting(key: string, value: unknown, valueType: string = 'string'): Observable<unknown> {
    return this.http.put(`${API_BASE}/settings/${key}`, {
      value: String(value),
      value_type: valueType,
    });
  }
  
  updateSettings(updates: Record<string, { value: unknown; value_type: string }>): Observable<unknown> {
    const payload: Record<string, { value: string; value_type: string }> = {};
    for (const [key, {value, value_type}] of Object.entries(updates)) {
      payload[key] = { value: String(value), value_type };
    }
    return this.http.put(`${API_BASE}/settings`, payload);
  }

  // ── Config ───────────────────────────────────────────────────────
  exportConfig(): Observable<unknown> {
    return this.http.get(`${API_BASE}/config/export`);
  }
}
