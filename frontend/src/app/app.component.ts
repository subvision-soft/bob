import { Component, OnInit, OnDestroy } from '@angular/core';
import { RouterOutlet, RouterLink, RouterLinkActive } from '@angular/router';
import { CommonModule } from '@angular/common';
import { Subject, takeUntil, interval } from 'rxjs';

import { MenubarModule } from 'primeng/menubar';
import { BadgeModule } from 'primeng/badge';
import { TagModule } from 'primeng/tag';
import { ToastModule } from 'primeng/toast';
import { ConfirmDialogModule } from 'primeng/confirmdialog';
import { MessageService, ConfirmationService } from 'primeng/api';

import { WebSocketService } from './core/websocket.service';
import { ApiService } from './core/api.service';
import { AppStore } from './store/app.store';

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [
    CommonModule,
    RouterOutlet,
    RouterLink,
    RouterLinkActive,
    MenubarModule,
    BadgeModule,
    TagModule,
    ToastModule,
    ConfirmDialogModule,
  ],
  providers: [MessageService, ConfirmationService],
  template: `
    <div class="svs-shell" [class.ws-connected]="ws.isConnected()">

      <!-- ── Top Nav Bar ─────────────────────────────────────────── -->
      <header class="svs-topbar">
        <div class="svs-topbar__brand">
          <i class="pi pi-video svs-topbar__logo"></i>
          <span class="svs-topbar__title">Subvision Studio</span>
          <span class="svs-topbar__version">v0.1</span>
        </div>

        <nav class="svs-topbar__nav">
          <a routerLink="/dashboard" routerLinkActive="active" class="svs-nav-item">
            <i class="pi pi-th-large"></i><span>Dashboard</span>
          </a>
          <a routerLink="/cameras" routerLinkActive="active" class="svs-nav-item">
            <i class="pi pi-camera"></i><span>Cameras</span>
          </a>
          <a routerLink="/rules" routerLinkActive="active" class="svs-nav-item">
            <i class="pi pi-sliders-h"></i><span>Rules</span>
          </a>
          <a routerLink="/events" routerLinkActive="active" class="svs-nav-item">
            <i class="pi pi-bolt"></i><span>Events</span>
          </a>
          <a routerLink="/monitoring" routerLinkActive="active" class="svs-nav-item">
            <i class="pi pi-chart-bar"></i><span>Monitor</span>
          </a>
          <a routerLink="/obs" routerLinkActive="active" class="svs-nav-item">
            <i class="pi pi-desktop"></i><span>OBS</span>
          </a>
          <a routerLink="/settings" routerLinkActive="active" class="svs-nav-item">
            <i class="pi pi-cog"></i><span>Settings</span>
          </a>
        </nav>

        <div class="svs-topbar__status">
          <!-- Program indicator -->
          <div class="svs-status-chip" *ngIf="store.programCamera() as cam">
            <span class="svs-dot svs-dot--red"></span>
            <span class="svs-status-chip__label">PROG</span>
            <strong>{{ cam.label }}</strong>
          </div>

          <!-- Preview indicator -->
          <div class="svs-status-chip" *ngIf="store.previewCamera() as cam">
            <span class="svs-dot svs-dot--green"></span>
            <span class="svs-status-chip__label">PREV</span>
            <strong>{{ cam.label }}</strong>
          </div>

          <!-- Backend health indicator -->
          <div class="svs-status-indicator" [class.connected]="isBackendHealthy()">
            <i class="pi" [class.pi-server]="isBackendHealthy()" [class.pi-exclamation-triangle]="!isBackendHealthy()"></i>
            <span>{{ isBackendHealthy() ? 'Backend' : 'Backend ⚠' }}</span>
          </div>

          <!-- OBS connection indicator -->
          <div class="svs-status-indicator" [class.connected]="isObsConnected()">
            <i class="pi" [class.pi-desktop]="isObsConnected()" [class.pi-exclamation-triangle]="!isObsConnected()"></i>
            <span>{{ isObsConnected() ? 'OBS' : 'OBS ⚠' }}</span>
          </div>

          <!-- WS connection -->
          <div class="svs-ws-indicator" [class.connected]="ws.isConnected()">
            <i class="pi" [class.pi-wifi]="ws.isConnected()" [class.pi-wifi-off]="!ws.isConnected()"></i>
            <span>{{ ws.isConnected() ? 'Live' : 'Reconnecting…' }}</span>
          </div>
        </div>
      </header>

      <!-- ── Main Content ────────────────────────────────────────── -->
      <main class="svs-content">
        <router-outlet />
      </main>

    </div>

    <p-toast position="bottom-right" [life]="4000" />
    <p-confirmDialog />
  `,
  styles: [`
    .svs-shell {
      display: flex;
      flex-direction: column;
      height: 100vh;
      overflow: hidden;
    }

    /* ── Topbar ─────────────────────────────────────────────────── */
    .svs-topbar {
      display: flex;
      align-items: center;
      gap: 1rem;
      height: 44px;
      min-height: 44px;
      background: var(--svs-bg-surface);
      border-bottom: 1px solid var(--svs-border);
      padding: 0 1rem;
      z-index: 100;
    }

    .svs-topbar__brand {
      display: flex;
      align-items: center;
      gap: 0.5rem;
      min-width: 180px;
    }
    .svs-topbar__logo {
      color: var(--svs-accent);
      font-size: 1.1rem;
    }
    .svs-topbar__title {
      font-weight: 700;
      font-size: 0.9rem;
      color: var(--svs-text-primary);
      letter-spacing: -0.02em;
    }
    .svs-topbar__version {
      font-size: 0.65rem;
      color: var(--svs-text-muted);
      background: var(--svs-bg-elevated);
      padding: 1px 5px;
      border-radius: 3px;
    }

    /* ── Nav ────────────────────────────────────────────────────── */
    .svs-topbar__nav {
      display: flex;
      align-items: center;
      gap: 0.125rem;
      flex: 1;
    }

    .svs-nav-item {
      display: flex;
      align-items: center;
      gap: 0.35rem;
      padding: 0.35rem 0.7rem;
      border-radius: var(--svs-radius-sm);
      color: var(--svs-text-secondary);
      text-decoration: none;
      font-size: 0.78rem;
      font-weight: 500;
      transition: color 0.15s, background 0.15s;

      i { font-size: 0.8rem; }

      &:hover { color: var(--svs-text-primary); background: var(--svs-bg-elevated); }
      &.active { color: var(--svs-accent); background: rgba(59,130,246,0.12); }
    }

    /* ── Status chips ───────────────────────────────────────────── */
    .svs-topbar__status {
      display: flex;
      align-items: center;
      gap: 0.75rem;
      margin-left: auto;
    }

    .svs-status-chip {
      display: flex;
      align-items: center;
      gap: 0.35rem;
      background: var(--svs-bg-elevated);
      border: 1px solid var(--svs-border);
      border-radius: 4px;
      padding: 3px 8px;
      font-size: 0.72rem;
    }
    .svs-status-chip__label {
      color: var(--svs-text-muted);
      font-weight: 600;
    }

    .svs-dot {
      width: 6px;
      height: 6px;
      border-radius: 50%;
      &--red   { background: var(--svs-program-color); animation: pulse-red 1.5s infinite; }
      &--green { background: var(--svs-preview-color); }
    }

    .svs-status-indicator {
      display: flex;
      align-items: center;
      gap: 0.3rem;
      font-size: 0.72rem;
      color: var(--svs-danger);
      i { font-size: 0.75rem; }
      &.connected { color: var(--svs-success); }
    }

    .svs-ws-indicator {
      display: flex;
      align-items: center;
      gap: 0.3rem;
      font-size: 0.72rem;
      color: var(--svs-danger);
      i { font-size: 0.75rem; }
      &.connected { color: var(--svs-success); }
    }

    /* ── Content ────────────────────────────────────────────────── */
    .svs-content {
      flex: 1;
      overflow: hidden;
      display: flex;
      flex-direction: column;
    }
  `],
})
export class AppComponent implements OnInit, OnDestroy {
  private destroy$ = new Subject<void>();

  constructor(
    public ws: WebSocketService,
    public store: AppStore,
    private api: ApiService,
  ) { }

  ngOnInit(): void {
    this._loadInitialData();
    this._subscribeToWebSocket();
    this._setupPolling();
    this._autoConnectObs();
  }

  private _loadInitialData(): void {
    // Load cameras
    this.api.getCameras().subscribe(cameras => this.store.setCameras(cameras));
    // Load OBS status
    this.api.getObsStatus().subscribe(status => this.store.updateObsStatus(status));
    // Load health
    this.api.getHealth().subscribe(h => this.store.health.set(h));
  }

  private _setupPolling(): void {
    // Poll every 10 seconds for health and OBS status
    interval(10000)
      .pipe(takeUntil(this.destroy$))
      .subscribe(() => {
        this.api.getHealth().subscribe(
          h => this.store.health.set(h),
          err => console.error('Health check failed:', err)
        );
        this.api.getObsStatus().subscribe(
          status => this.store.updateObsStatus(status),
          err => console.error('OBS status check failed:', err)
        );
      });
  }

  private _autoConnectObs(): void {
    // Try to get stored OBS connection settings
    const obsSettings = localStorage.getItem('obs_settings');
    if (obsSettings) {
      try {
        const settings = JSON.parse(obsSettings);
        if (settings.url && settings.password) {
          this.api.connectObs(settings.url, settings.password).subscribe(
            () => console.log('Auto-connected to OBS'),
            err => console.error('Failed to auto-connect to OBS:', err)
          );
        }
      } catch (e) {
        console.error('Failed to parse OBS settings:', e);
      }
    }
  }

  isBackendHealthy(): boolean {
    return this.store.health()?.status === 'ok';
  }

  isObsConnected(): boolean {
    return this.store.obsStatus()?.state === 'CONNECTED';
  }

  private _subscribeToWebSocket(): void {
    // Camera scores
    this.ws.on('camera_scores').pipe(takeUntil(this.destroy$)).subscribe(msg => {
      if (Array.isArray(msg.data)) this.store.updateCameraContexts(msg.data as any);
    });

    // Global context
    this.ws.on('global_context').pipe(takeUntil(this.destroy$)).subscribe(msg => {
      if (msg.data) this.store.updateGlobalContext(msg.data as any);
    });

    // Decision trace
    this.ws.on('decision_trace').pipe(takeUntil(this.destroy$)).subscribe(msg => {
      if (msg.data) this.store.updateDecisionTrace(msg.data as any);
    });

    // Stream health
    this.ws.on('stream_health').pipe(takeUntil(this.destroy$)).subscribe(msg => {
      if (msg.data) this.store.updateStreamHealth(msg.data as any);
    });

    // Snapshots
    this.ws.on('snapshot').pipe(takeUntil(this.destroy$)).subscribe(msg => {
      if (msg.camera_id && msg.data) {
        this.store.updateSnapshot(msg.camera_id, msg.data as string);
      }
    });

    // OBS state
    this.ws.on('obs_state').pipe(takeUntil(this.destroy$)).subscribe(msg => {
      if (msg.data) this.store.updateObsStatus(msg.data as any);
    });
  }

  ngOnDestroy(): void {
    this.destroy$.next();
    this.destroy$.complete();
  }
}
