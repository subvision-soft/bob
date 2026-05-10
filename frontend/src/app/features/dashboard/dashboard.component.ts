import { Component, OnInit, OnDestroy, computed } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Subject, takeUntil } from 'rxjs';

import { SplitterModule } from 'primeng/splitter';
import { PanelModule } from 'primeng/panel';
import { TagModule } from 'primeng/tag';
import { BadgeModule } from 'primeng/badge';
import { ButtonModule } from 'primeng/button';
import { TooltipModule } from 'primeng/tooltip';
import { ProgressBarModule } from 'primeng/progressbar';
import { ScrollPanelModule } from 'primeng/scrollpanel';

import { AppStore } from '../../store/app.store';
import { ApiService, Camera } from '../../core/api.service';
import { WebSocketService } from '../../core/websocket.service';

@Component({
  selector: 'app-dashboard',
  standalone: true,
  imports: [
    CommonModule,
    PanelModule,
    TagModule,
    BadgeModule,
    ButtonModule,
    TooltipModule,
    ProgressBarModule,
    ScrollPanelModule,
  ],
  template: `
    <div class="dashboard">
      <!-- ── LEFT: Camera Grid ──────────────────────────────────── -->
      <div class="svs-card panel-col">
            <div class="svs-section-title">
              <i class="pi pi-camera"></i> CAMERAS
              <span class="svs-badge">{{ store.cameras().length }}</span>
            </div>

            <div class="camera-grid">
              @for (camera of store.cameras(); track camera.id) {
                <div
                  class="svs-camera-thumb"
                  [class.on-air]="getCameraContext(camera.id)?.is_on_air"
                  [class.preview]="isPreview(camera.id)"
                  (click)="manualSwitch(camera)"
                  [pTooltip]="camera.name"
                >
                  <!-- Snapshot or placeholder -->
                  <img *ngIf="store.cameraSnapshots()[camera.id]"
                       [src]="'data:image/jpeg;base64,' + store.cameraSnapshots()[camera.id]"
                       class="cam-img" />
                  <div *ngIf="!store.cameraSnapshots()[camera.id]" class="cam-placeholder">
                    <i class="pi pi-video"></i>
                  </div>

                  <!-- ON AIR overlay -->
                  <div *ngIf="getCameraContext(camera.id)?.is_on_air" class="cam-overlay cam-overlay--onair">
                    <span>● ON AIR</span>
                  </div>
                  <div *ngIf="isPreview(camera.id) && !getCameraContext(camera.id)?.is_on_air" class="cam-overlay cam-overlay--preview">
                    <span>● PREVIEW</span>
                  </div>

                  <!-- Label + score bar -->
                  <div class="cam-footer">
                    <span class="cam-label">{{ camera.label }}</span>
                    <span class="cam-score">{{ getCameraContext(camera.id)?.interest_score | number:'1.0-0' }}</span>
                  </div>
                  <div class="svs-score-bar">
                    <div
                      class="fill"
                      [class.high]="(getCameraContext(camera.id)?.interest_score ?? 0) >= 70"
                      [class.med]="(getCameraContext(camera.id)?.interest_score ?? 0) >= 40 && (getCameraContext(camera.id)?.interest_score ?? 0) < 70"
                      [class.low]="(getCameraContext(camera.id)?.interest_score ?? 0) < 40"
                      [style.width]="(getCameraContext(camera.id)?.interest_score ?? 0) + '%'"
                    ></div>
                  </div>
                </div>
              }

              @if (store.cameras().length === 0) {
                <div class="empty-state">
                  <i class="pi pi-camera"></i>
                  <p>No cameras configured</p>
                  <small>Go to <strong>Cameras</strong> to add one</small>
                </div>
              }
            </div>
        </div>

      <!-- ── CENTER: Program / Preview monitors ─────────────────── -->
      <div class="svs-card panel-col panel-col--center">

            <!-- Program monitor -->
            <div class="monitor monitor--program">
              <div class="monitor__header">
                <span class="monitor__dot"></span>
                <span class="monitor__label">PROGRAM</span>
                <span class="monitor__cam-name">{{ getProgramLabel() }}</span>
                @if (store.programCamera()) {
                  <span class="monitor__time">
                    {{ formatDuration(store.globalContext()?.time_on_current_camera_ms ?? 0) }}
                  </span>
                }
              </div>
              <div class="monitor__screen monitor__screen--program">
                @if (programSnap()) {
                  <img [src]="'data:image/jpeg;base64,' + programSnap()" />
                } @else {
                  <div class="monitor__placeholder">
                    <i class="pi pi-video"></i>
                    <span>{{ getProgramLabel() }}</span>
                  </div>
                }
              </div>
            </div>

            <!-- Preview monitor -->
            <div class="monitor monitor--preview">
              <div class="monitor__header">
                <span class="monitor__dot monitor__dot--green"></span>
                <span class="monitor__label">PREVIEW</span>
                <span class="monitor__cam-name">{{ getPreviewLabel() }}</span>
              </div>
              <div class="monitor__screen monitor__screen--preview">
                @if (previewSnap()) {
                  <img [src]="'data:image/jpeg;base64,' + previewSnap()" />
                } @else {
                  <div class="monitor__placeholder monitor__placeholder--preview">
                    <i class="pi pi-video"></i>
                    <span>{{ getPreviewLabel() }}</span>
                  </div>
                }
              </div>
            </div>

            <!-- Control bar -->
            <div class="control-bar">
              <div class="control-bar__info">
                <span>Switches: <strong>{{ store.globalContext()?.total_switches ?? 0 }}</strong></span>
                <span>Events: <strong>{{ store.globalContext()?.events_processed ?? 0 }}</strong></span>
                <span [class.active]="store.globalContext()?.is_global_cooldown_active">
                  <i class="pi pi-clock"></i>
                  {{ store.globalContext()?.is_global_cooldown_active ? 'COOLDOWN' : 'Ready' }}
                </span>
              </div>

              <div class="control-bar__actions">
                <p-button
                  icon="pi pi-refresh"
                  label="Reload Cameras"
                  severity="secondary"
                  size="small"
                  (onClick)="reloadCameras()"
                />
              </div>
            </div>

            <!-- Last switch reason -->
            @if (store.globalContext()?.last_switch_reason; as reason) {
              <div class="switch-reason">
                <i class="pi pi-arrow-right-arrow-left"></i>
                <span>{{ reason }}</span>
              </div>
            }

          </div>

      <!-- ── RIGHT: Event log + Decision trace ───────────────────── -->
      <div class="svs-card panel-col">

            <!-- Decision trace -->
            <div class="svs-section-title">
              <i class="pi pi-cpu"></i> DECISION ENGINE
            </div>

            @if (store.decisionTrace(); as trace) {
              <div class="decision-block">
                @if (trace.switch_triggered) {
                  <div class="decision-winner">
                    <span class="decision-winner__label">↳ SWITCHED TO</span>
                    <strong class="decision-winner__cam">{{ getCameraLabel(trace.winner) }}</strong>
                    <span class="decision-winner__score">{{ trace.winner_score | number:'1.0-1' }}</span>
                  </div>
                }
                @if (trace.blocked_reason) {
                  <div class="decision-blocked">
                    <i class="pi pi-ban"></i>
                    <span>{{ trace.blocked_reason }}</span>
                  </div>
                }

                <div class="decision-candidates">
                  @for (c of trace.candidates; track c.camera_id) {
                    <div class="candidate" [class.winner]="c.camera_id === trace.winner">
                      <span class="candidate__name">{{ getCameraLabel(c.camera_id) }}</span>
                      <div class="candidate__bar">
                        <div class="candidate__fill"
                          [style.width]="c.score + '%'"
                          [class.high]="c.score >= 70"
                          [class.med]="c.score >= 40 && c.score < 70"
                        ></div>
                      </div>
                      <span class="candidate__score">{{ c.score | number:'1.0-0' }}</span>
                      <i *ngIf="c.in_cooldown" class="pi pi-clock" pTooltip="In cooldown" style="color: var(--svs-warning); font-size:0.7rem"></i>
                    </div>
                  }
                </div>
              </div>
            }

            <!-- Live event log -->
            <div class="svs-section-title" style="margin-top: 0.5rem">
              <i class="pi pi-list"></i> LIVE EVENTS
            </div>
            <div class="event-log">
              @for (event of store.recentEvents().slice(0, 30); track event.id) {
                <div class="event-entry" [class]="'severity-' + event.severity.toLowerCase()">
                  <span class="event-entry__type">{{ event.event_type }}</span>
                  <span class="event-entry__time">{{ event.received_at | date:'HH:mm:ss.SSS' }}</span>
                </div>
              }
              @if (store.recentEvents().length === 0) {
                <div class="empty-state empty-state--compact">
                  <i class="pi pi-bolt"></i>
                  <span>Waiting for events…</span>
                </div>
              }
            </div>

          </div>
    </div>
  `,
  styles: [`
    .dashboard {
      padding: 1.5rem;
      height: 100%;
      display: grid;
      grid-template-columns: minmax(260px, 1fr) minmax(500px, 2.5fr) minmax(300px, 1.2fr);
      gap: 1rem;
      overflow-y: auto;
    }

    :host ::ng-deep .dashboard-splitter {
      height: 100% !important;
    }

    /* ── Column layout ─────────────────────────────────── */
    .panel-col {
      height: 100%;
      display: flex;
      flex-direction: column;
      overflow: hidden;
      padding: 0.5rem;
    }

    .panel-col--center {
      padding: 0.5rem;
      gap: 0.5rem;
    }

    /* ── Camera grid ────────────────────────────────────── */
    .camera-grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 6px;
      padding: 6px;
      overflow-y: auto;
      flex: 1;
    }

    .svs-camera-thumb {
      position: relative;
      aspect-ratio: 16/9;
      background: #000;
      border-radius: 4px;
      overflow: hidden;
      border: 2px solid transparent;
      cursor: pointer;
      transition: border-color 0.2s, box-shadow 0.2s;

      &:hover { border-color: var(--svs-accent); }
      &.on-air { border-color: var(--svs-program-color) !important; box-shadow: 0 0 12px rgba(239,68,68,0.5); }
      &.preview { border-color: var(--svs-preview-color) !important; }
    }

    .cam-img { width: 100%; height: 100%; object-fit: cover; display: block; }
    .cam-placeholder {
      display: flex; align-items: center; justify-content: center;
      height: 100%; color: var(--svs-text-muted); font-size: 1.2rem;
    }

    .cam-overlay {
      position: absolute; top: 4px; left: 4px;
      font-size: 0.6rem; font-weight: 700; letter-spacing: 0.05em;
      padding: 2px 5px; border-radius: 2px;
      &--onair  { background: var(--svs-program-color); color: #fff; animation: pulse-red 1.5s infinite; }
      &--preview { background: var(--svs-preview-color); color: #fff; }
    }

    .cam-footer {
      position: absolute; bottom: 0; left: 0; right: 0;
      display: flex; justify-content: space-between; align-items: center;
      background: linear-gradient(transparent, rgba(0,0,0,0.85));
      padding: 4px 5px 2px; font-size: 0.65rem;
    }
    .cam-label { font-weight: 600; color: #fff; }
    .cam-score { color: var(--svs-accent); font-family: var(--svs-font-mono); }

    /* ── Monitors ────────────────────────────────────────── */
    .monitor {
      display: flex;
      flex-direction: column;
      border-radius: var(--svs-radius-sm);
      overflow: hidden;
      border: 1px solid var(--svs-border);
      flex: 1;
      box-shadow: var(--svs-shadow-lg);
      background: var(--svs-bg-elevated);
    }
    .monitor--program { border: 2px solid var(--svs-program-color); box-shadow: 0 0 40px rgba(239,68,68,0.25); }
    .monitor--preview { border: 2px solid var(--svs-preview-color); box-shadow: 0 0 30px rgba(16,185,129,0.15); flex: 0.6; }

    .monitor__header {
      display: flex; align-items: center; gap: 0.5rem;
      padding: 4px 8px;
      background: var(--svs-bg-elevated);
      font-size: 0.7rem; font-weight: 700; letter-spacing: 0.06em;
    }
    .monitor__dot {
      width: 7px; height: 7px; border-radius: 50%;
      background: var(--svs-program-color); animation: pulse-red 1.5s infinite;
      &--green { background: var(--svs-preview-color); animation: none; }
    }
    .monitor__label { color: var(--svs-text-muted); }
    .monitor__cam-name { color: var(--svs-text-primary); }
    .monitor__time { margin-left: auto; color: var(--svs-text-muted); font-family: var(--svs-font-mono); }

    .monitor__screen {
      flex: 1; display: flex; background: #000;
      img { width: 100%; height: 100%; object-fit: cover; }
      &--program { border-top: 1px solid var(--svs-program-color); }
      &--preview { border-top: 1px solid var(--svs-preview-color); }
    }
    .monitor__placeholder {
      flex: 1; display: flex; flex-direction: column; align-items: center;
      justify-content: center; gap: 0.5rem; color: var(--svs-text-muted);
      font-size: 0.85rem;
      i { font-size: 1.5rem; }
    }

    /* ── Control bar ────────────────────────────────────── */
    .control-bar {
      display: flex; align-items: center; justify-content: space-between;
      background: var(--svs-bg-elevated);
      border: 1px solid var(--svs-border);
      border-radius: var(--svs-radius-sm);
      padding: 4px 8px; font-size: 0.72rem;
    }
    .control-bar__info {
      display: flex; gap: 1rem; color: var(--svs-text-secondary);
      .active { color: var(--svs-warning); }
    }

    .switch-reason {
      display: flex; align-items: center; gap: 0.4rem;
      font-size: 0.7rem; color: var(--svs-text-muted);
      font-family: var(--svs-font-mono);
      padding: 2px 4px;
    }

    /* ── Decision panel ──────────────────────────────────── */
    .decision-block {
      padding: 6px;
      display: flex; flex-direction: column; gap: 4px;
    }
    .decision-winner {
      display: flex; align-items: center; gap: 0.5rem;
      background: rgba(239,68,68,0.1); border: 1px solid rgba(239,68,68,0.3);
      border-radius: 4px; padding: 4px 8px; font-size: 0.75rem;
      animation: slide-in-right 0.2s ease;
    }
    .decision-winner__label { color: var(--svs-text-muted); font-size: 0.65rem; }
    .decision-winner__cam { color: var(--svs-text-primary); }
    .decision-winner__score { margin-left: auto; color: var(--svs-accent); font-family: var(--svs-font-mono); }

    .decision-blocked {
      display: flex; align-items: center; gap: 0.5rem;
      color: var(--svs-warning); font-size: 0.72rem; padding: 2px 4px;
    }

    .decision-candidates {
      display: flex; flex-direction: column; gap: 3px;
    }
    .candidate {
      display: flex; align-items: center; gap: 6px;
      padding: 3px 6px; border-radius: 3px; font-size: 0.7rem;
      &.winner { background: rgba(59,130,246,0.1); }
    }
    .candidate__name { width: 80px; color: var(--svs-text-secondary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .candidate__bar {
      flex: 1; height: 3px; background: var(--svs-border); border-radius: 2px; overflow: hidden;
    }
    .candidate__fill {
      height: 100%; border-radius: 2px; background: var(--svs-text-muted);
      transition: width 0.3s ease;
      &.high { background: var(--svs-success); }
      &.med  { background: var(--svs-warning); }
    }
    .candidate__score { width: 28px; text-align: right; font-family: var(--svs-font-mono); color: var(--svs-accent); }

    /* ── Event log ───────────────────────────────────────── */
    .event-log {
      flex: 1; overflow-y: auto; padding: 4px;
      display: flex; flex-direction: column; gap: 1px;
    }
    .event-entry {
      display: flex; justify-content: space-between; align-items: center;
      padding: 3px 6px; border-radius: 3px; font-size: 0.7rem;
      font-family: var(--svs-font-mono);
      background: var(--svs-bg-elevated);
      animation: slide-in-right 0.15s ease;

      &.severity-critical { border-left: 2px solid var(--svs-danger); }
      &.severity-high     { border-left: 2px solid var(--svs-critical); }
      &.severity-medium   { border-left: 2px solid var(--svs-accent); }
      &.severity-low      { border-left: 2px solid var(--svs-border); }
    }
    .event-entry__type { color: var(--svs-text-primary); font-weight: 500; }
    .event-entry__time { color: var(--svs-text-muted); font-size: 0.65rem; }

    /* ── Misc ─────────────────────────────────────────────── */
    .svs-badge {
      background: var(--svs-bg-elevated); color: var(--svs-text-muted);
      font-size: 0.65rem; padding: 1px 5px; border-radius: 3px; margin-left: 4px;
    }
    .empty-state {
      display: flex; flex-direction: column; align-items: center; justify-content: center;
      gap: 0.5rem; padding: 2rem; color: var(--svs-text-muted); text-align: center;
      i { font-size: 1.5rem; }
      &--compact { padding: 1rem; font-size: 0.78rem; }
    }
  `],
})
export class DashboardComponent implements OnInit, OnDestroy {
  private destroy$ = new Subject<void>();

  constructor(
    public store: AppStore,
    private api: ApiService,
    private ws: WebSocketService,
  ) { }

  ngOnInit(): void {
    // Subscribe to live events from WS
    this.ws.on('event_received').pipe(takeUntil(this.destroy$)).subscribe(msg => {
      if (msg.data) this.store.pushEvent(msg.data as any);
    });
  }

  getCameraContext(cameraId: string) {
    return this.store.cameraContexts().find(c => c.camera_id === cameraId);
  }

  getCameraLabel(cameraId: string | null): string {
    if (!cameraId) return '—';
    return this.store.cameras().find(c => c.id === cameraId)?.label ?? cameraId;
  }

  isPreview(cameraId: string): boolean {
    return this.store.globalContext()?.preview_camera_id === cameraId;
  }

  programSnap = computed(() => {
    const cam = this.store.programCamera();
    if (cam) return this.store.cameraSnapshots()[cam.id] ?? null;
    const scene = this.store.obsStatus()?.current_program ?? null;
    const obsCam = this.resolveCameraByScene(scene);
    return obsCam ? this.store.cameraSnapshots()[obsCam.id] ?? null : null;
  });

  previewSnap = computed(() => {
    const cam = this.store.previewCamera();
    if (cam) return this.store.cameraSnapshots()[cam.id] ?? null;
    const scene = this.store.obsStatus()?.current_preview ?? null;
    const obsCam = this.resolveCameraByScene(scene);
    return obsCam ? this.store.cameraSnapshots()[obsCam.id] ?? null : null;
  });

  manualSwitch(camera: Camera): void {
    this.api.setObsScene(camera.obs_scene_name || '', 'program').subscribe();
  }

  reloadCameras(): void {
    this.api.getCameras().subscribe(cameras => this.store.setCameras(cameras));
  }

  formatDuration(ms: number): string {
    const s = Math.floor(ms / 1000);
    const m = Math.floor(s / 60);
    return `${m}:${(s % 60).toString().padStart(2, '0')}`;
  }

  getProgramLabel(): string {
    const cam = this.store.programCamera();
    if (cam) return cam.label;
    const scene = this.store.obsStatus()?.current_program;
    const obsCam = this.resolveCameraByScene(scene ?? null);
    return obsCam?.label ?? scene ?? 'No Program';
  }

  getPreviewLabel(): string {
    const cam = this.store.previewCamera();
    if (cam) return cam.label;
    const scene = this.store.obsStatus()?.current_preview;
    const obsCam = this.resolveCameraByScene(scene ?? null);
    return obsCam?.label ?? scene ?? 'No Preview';
  }

  private resolveCameraByScene(sceneName: string | null): Camera | null {
    if (!sceneName) return null;
    const scene = sceneName.trim();
    return this.store.cameras().find(c =>
      c.source_type === 'obs_scene'
      && (c.obs_scene_name === scene || c.source_url === scene)
    ) ?? null;
  }

  ngOnDestroy(): void {
    this.destroy$.next();
    this.destroy$.complete();
  }
}
