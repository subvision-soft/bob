/**
 * App Store — Angular Signals-based reactive state management.
 * Single source of truth for the entire frontend state.
 */

import { Injectable, signal, computed } from '@angular/core';
import { Camera, CameraContext, OBSStatus, EventLogEntry, HealthStatus } from '../core/api.service';

export interface DecisionTrace {
  cycle_at: number;
  candidates: CameraCandidate[];
  winner: string | null;
  winner_score: number;
  winner_reason: string;
  switch_triggered: boolean;
  idle_rotation_triggered?: boolean;
  scene_max_display_triggered?: boolean;
  rotated_scene?: string | null;
  blocked_reason: string | null;
  global_cooldown_active: boolean;
  min_display_enforced: boolean;
}

export interface CameraCandidate {
  camera_id: string;
  score: number;
  mode: string;
  pending: boolean;
  in_cooldown: boolean;
  on_air: boolean;
  event_priority?: number;
  activity_weight?: number;
  critical_bonus?: number;
}

export interface GlobalContext {
  competition_state: string;
  competition_id: string | null;
  program_camera_id: string | null;
  preview_camera_id: string | null;
  program_scene_name?: string | null;
  program_scene_since_ms?: number;
  time_on_current_camera_ms: number;
  is_global_cooldown_active: boolean;
  total_switches: number;
  events_processed: number;
  last_switch_reason: string | null;
}

export interface StreamHealth {
  [cameraId: string]: {
    fps: number;
    frames_received: number;
    frames_dropped: number;
    latency_ms: number;
    status: string;
  };
}

export interface LogEntry {
  timestamp: number;
  level: string;
  message: string;
  data?: Record<string, unknown>;
}

@Injectable({ providedIn: 'root' })
export class AppStore {
  // ── Cameras ──────────────────────────────────────────────────────
  readonly cameras = signal<Camera[]>([]);
  readonly cameraContexts = signal<CameraContext[]>([]);
  readonly cameraSnapshots = signal<Record<string, string>>({});  // camera_id → base64 JPEG

  // ── Real-time state ───────────────────────────────────────────────
  readonly globalContext = signal<GlobalContext | null>(null);
  readonly decisionTrace = signal<DecisionTrace | null>(null);
  readonly streamHealth = signal<StreamHealth>({});

  // ── OBS ──────────────────────────────────────────────────────────
  readonly obsStatus = signal<OBSStatus | null>(null);

  // ── Events ───────────────────────────────────────────────────────
  readonly recentEvents = signal<EventLogEntry[]>([]);

  // ── Logs ─────────────────────────────────────────────────────────
  readonly logs = signal<LogEntry[]>([]);
  readonly MAX_LOGS = 200;

  // ── Health ───────────────────────────────────────────────────────
  readonly health = signal<HealthStatus | null>(null);
  readonly wsConnected = signal(false);

  // ── Computed ─────────────────────────────────────────────────────
  readonly programCamera = computed(() => {
    const programId = this.globalContext()?.program_camera_id;
    return this.cameras().find(c => c.id === programId) ?? null;
  });

  readonly previewCamera = computed(() => {
    const previewId = this.globalContext()?.preview_camera_id;
    return this.cameras().find(c => c.id === previewId) ?? null;
  });

  readonly sortedContexts = computed(() =>
    [...this.cameraContexts()].sort((a, b) => b.interest_score - a.interest_score)
  );

  readonly activeCooldowns = computed(() =>
    this.cameraContexts().filter(c => c.is_in_cooldown)
  );

  // ── Mutations ─────────────────────────────────────────────────────

  updateCameraContexts(contexts: CameraContext[]): void {
    this.cameraContexts.set(contexts);
  }

  updateGlobalContext(ctx: GlobalContext): void {
    this.globalContext.set(ctx);
  }

  updateDecisionTrace(trace: DecisionTrace): void {
    this.decisionTrace.set(trace);
  }

  updateStreamHealth(health: StreamHealth): void {
    this.streamHealth.set(health);
  }

  updateObsStatus(status: OBSStatus): void {
    this.obsStatus.set(status);
  }

  pushEvent(event: EventLogEntry): void {
    this.recentEvents.update(events => [event, ...events].slice(0, 100));
  }

  pushLog(entry: LogEntry): void {
    this.logs.update(logs => [entry, ...logs].slice(0, this.MAX_LOGS));
  }

  updateSnapshot(cameraId: string, base64: string): void {
    this.cameraSnapshots.update(snaps => ({ ...snaps, [cameraId]: base64 }));
  }

  setCameras(cameras: Camera[]): void {
    this.cameras.set(cameras);
  }
}
