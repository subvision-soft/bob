import { Component, OnInit, OnDestroy, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Subject, takeUntil, interval } from 'rxjs';

import { SplitterModule } from 'primeng/splitter';
import { PanelModule } from 'primeng/panel';
import { TableModule } from 'primeng/table';
import { ButtonModule } from 'primeng/button';
import { TagModule } from 'primeng/tag';
import { BadgeModule } from 'primeng/badge';
import { ProgressBarModule } from 'primeng/progressbar';
import { TooltipModule } from 'primeng/tooltip';
import { TimelineModule } from 'primeng/timeline';
import { KnobModule } from 'primeng/knob';
import { FormsModule } from '@angular/forms';

import { AppStore } from '../../store/app.store';
import { ApiService } from '../../core/api.service';
import { WebSocketService } from '../../core/websocket.service';

export interface SwitchRecord {
  from_camera: string | null;
  to_camera: string;
  reason: string;
  score: number;
  event_type: string | null;
  wall_time: number;
}


@Component({
  selector: 'app-monitoring',
  standalone: true,
  imports: [
    CommonModule, FormsModule,
    SplitterModule, PanelModule, TableModule, ButtonModule,
    TagModule, BadgeModule, ProgressBarModule, TooltipModule,
    TimelineModule, KnobModule,
  ],
  template: `
    <div class="monitoring-page">

      <p-splitter [panelSizes]="[50, 50]" styleClass="h-full">

        <!-- LEFT: Camera scores + decision engine debug -->
        <ng-template pTemplate>
          <div class="monitor-col">

            <div class="svs-section-title">
              <i class="pi pi-chart-bar"></i> CAMERA SCORES (LIVE)
            </div>

            <div class="scores-list">
              @for (ctx of store.sortedContexts(); track ctx.camera_id) {
                <div class="score-card" [class.on-air]="ctx.is_on_air" [class.in-cooldown]="ctx.is_in_cooldown">
                  <div class="score-card__header">
                    <span class="score-card__name">{{ getCameraById(ctx.camera_id)?.label ?? ctx.camera_id }}</span>

                    @if (ctx.is_on_air) {
                      <p-tag value="ON AIR" severity="danger" />
                    }
                    @if (ctx.is_in_cooldown) {
                      <p-tag value="COOLDOWN" severity="warning" />
                    }
                    @if (ctx.pending_mode) {
                      <p-tag [value]="ctx.pending_mode" severity="info" />
                    }

                    <span class="score-card__val">{{ ctx.interest_score | number:'1.0-1' }}</span>
                  </div>

                  <div class="svs-score-bar" style="margin: 4px 0">
                    <div class="fill"
                      [class.high]="ctx.interest_score >= 70"
                      [class.med]="ctx.interest_score >= 40 && ctx.interest_score < 70"
                      [style.width]="ctx.interest_score + '%'"
                    ></div>
                  </div>

                  <div class="score-card__meta">
                    <span>Last event: <strong>{{ ctx.last_event_type ?? '—' }}</strong></span>
                    <span>Activity: <strong>{{ ctx.time_since_last_activity_s | number:'1.0-1' }}s ago</strong></span>
                    <span>Switches: <strong>{{ ctx.switch_count }}</strong></span>
                    @if (ctx.is_in_cooldown) {
                      <span class="cooldown-badge">CD: {{ ctx.cooldown_remaining_ms | number:'1.0-0' }}ms</span>
                    }
                  </div>

                  <!-- Recent events -->
                  <div class="recent-events">
                    @for (et of ctx.recent_events.slice(-5).reverse(); track $index) {
                      <span class="recent-event-chip">{{ et }}</span>
                    }
                  </div>
                </div>
              }

              @if (store.cameraContexts().length === 0) {
                <div class="empty-info">
                  <i class="pi pi-chart-bar"></i>
                  <p>No camera data yet. Add cameras and start the engine.</p>
                </div>
              }
            </div>
          </div>
        </ng-template>

        <!-- RIGHT: Decision trace + switch history -->
        <ng-template pTemplate>
          <div class="monitor-col">

            <!-- Decision Trace -->
            <div class="svs-section-title">
              <i class="pi pi-cpu"></i> LAST DECISION TRACE
            </div>

            @if (store.decisionTrace(); as trace) {
              <div class="trace-block">
                <div class="trace-row">
                  <span class="trace-label">Cycle Time</span>
                  <span class="trace-val">{{ trace.cycle_at | date:'HH:mm:ss.SSS' }}</span>
                </div>
                <div class="trace-row">
                  <span class="trace-label">Winner</span>
                  <span class="trace-val accent">{{ getCameraLabel(trace.winner) }}</span>
                </div>
                <div class="trace-row">
                  <span class="trace-label">Score</span>
                  <span class="trace-val">{{ trace.winner_score | number:'1.0-2' }}</span>
                </div>
                <div class="trace-row">
                  <span class="trace-label">Reason</span>
                  <span class="trace-val">{{ trace.winner_reason || '—' }}</span>
                </div>
                <div class="trace-row">
                  <span class="trace-label">Switch Triggered</span>
                  <p-tag [value]="trace.switch_triggered ? 'YES' : 'NO'"
                         [severity]="trace.switch_triggered ? 'success' : 'secondary'" />
                </div>
                @if (trace.blocked_reason) {
                  <div class="trace-row trace-row--blocked">
                    <i class="pi pi-ban"></i>
                    <span>{{ trace.blocked_reason }}</span>
                  </div>
                }
                @if (trace.global_cooldown_active) {
                  <div class="trace-row trace-row--warn">
                    <i class="pi pi-clock"></i>
                    <span>Global cooldown active</span>
                  </div>
                }
                @if (trace.min_display_enforced) {
                  <div class="trace-row trace-row--warn">
                    <i class="pi pi-lock"></i>
                    <span>Min display duration not reached</span>
                  </div>
                }
              </div>
            } @else {
              <div class="empty-info"><i class="pi pi-cpu"></i><p>Waiting for decision cycle…</p></div>
            }

            <!-- Switch History -->
            <div class="svs-section-title" style="margin-top: 0.75rem">
              <i class="pi pi-history"></i> SWITCH HISTORY
            </div>

            <div class="history-list">
              @for (sw of switchHistory(); track sw.wall_time) {
                <div class="history-entry">
                  <div class="history-entry__cameras">
                    <span class="history-cam">{{ sw.from_camera ?? '—' }}</span>
                    <i class="pi pi-arrow-right" style="color: var(--svs-accent); font-size: 0.7rem"></i>
                    <span class="history-cam history-cam--to">{{ sw.to_camera }}</span>
                  </div>
                  <div class="history-entry__meta">
                    <span class="history-reason">{{ sw.reason }}</span>
                    <span class="history-time">{{ (sw.wall_time * 1000) | date:'HH:mm:ss' }}</span>
                  </div>
                </div>
              }
              @if (switchHistory().length === 0) {
                <div class="empty-info compact"><i class="pi pi-history"></i><p>No switches yet</p></div>
              }
            </div>

          </div>
        </ng-template>

      </p-splitter>
    </div>
  `,
  styles: [`
    .monitoring-page { height: 100%; display: flex; flex-direction: column; overflow: hidden; }
    :host ::ng-deep .p-splitter { height: 100% !important; }

    .monitor-col { display: flex; flex-direction: column; height: 100%; overflow: hidden; }

    /* Scores */
    .scores-list { flex: 1; overflow-y: auto; padding: 6px; display: flex; flex-direction: column; gap: 6px; }
    .score-card {
      background: var(--svs-bg-card); border: 1px solid var(--svs-border);
      border-radius: var(--svs-radius-md); padding: 8px 10px;
      transition: border-color 0.2s;
      &.on-air    { border-color: var(--svs-program-color); box-shadow: 0 0 10px rgba(239,68,68,0.3); }
      &.in-cooldown { border-color: var(--svs-warning); }
    }
    .score-card__header {
      display: flex; align-items: center; gap: 0.4rem; margin-bottom: 4px;
    }
    .score-card__name { font-weight: 600; font-size: 0.82rem; flex: 1; }
    .score-card__val { font-family: var(--svs-font-mono); font-size: 0.9rem; color: var(--svs-accent); margin-left: auto; }
    .score-card__meta {
      display: flex; flex-wrap: wrap; gap: 0.75rem; font-size: 0.68rem;
      color: var(--svs-text-secondary); margin-top: 4px;
    }
    .cooldown-badge { color: var(--svs-warning); font-weight: 600; }
    .recent-events { display: flex; flex-wrap: wrap; gap: 3px; margin-top: 4px; }
    .recent-event-chip {
      font-size: 0.6rem; padding: 1px 4px; border-radius: 2px;
      background: var(--svs-bg-elevated); color: var(--svs-text-muted);
    }

    /* Trace */
    .trace-block {
      padding: 6px 8px; background: var(--svs-bg-card);
      border: 1px solid var(--svs-border); border-radius: var(--svs-radius-md); margin: 4px;
    }
    .trace-row {
      display: flex; align-items: center; gap: 0.5rem; padding: 3px 0;
      border-bottom: 1px solid var(--svs-border-subtle); font-size: 0.75rem;
      &:last-child { border-bottom: none; }
      &--blocked { color: var(--svs-danger); }
      &--warn    { color: var(--svs-warning); }
    }
    .trace-label { width: 120px; color: var(--svs-text-muted); font-size: 0.68rem; }
    .trace-val { color: var(--svs-text-primary); font-family: var(--svs-font-mono); &.accent { color: var(--svs-accent); } }

    /* History */
    .history-list { flex: 1; overflow-y: auto; padding: 4px; display: flex; flex-direction: column; gap: 3px; }
    .history-entry {
      background: var(--svs-bg-elevated); border-radius: 4px; padding: 5px 8px;
      display: flex; flex-direction: column; gap: 2px;
      animation: slide-in-right 0.2s ease;
    }
    .history-entry__cameras { display: flex; align-items: center; gap: 6px; font-size: 0.75rem; }
    .history-cam { color: var(--svs-text-secondary); &--to { color: var(--svs-text-primary); font-weight: 600; } }
    .history-entry__meta { display: flex; justify-content: space-between; font-size: 0.68rem; color: var(--svs-text-muted); }
    .history-reason { font-family: var(--svs-font-mono); color: var(--svs-accent); }
    .history-time { font-family: var(--svs-font-mono); }

    .empty-info {
      display: flex; flex-direction: column; align-items: center; justify-content: center;
      gap: 0.5rem; padding: 2rem; color: var(--svs-text-muted); text-align: center;
      i { font-size: 1.5rem; }
      &.compact { padding: 0.75rem; }
    }
  `],
})
export class MonitoringComponent implements OnInit, OnDestroy {
  private destroy$ = new Subject<void>();
  switchHistory = signal<SwitchRecord[]>([]);

  constructor(
    public store: AppStore,
    private api: ApiService,
  ) {}

  ngOnInit(): void {
    this._loadHistory();
    // Refresh switch history every 5s
    interval(5000).pipe(takeUntil(this.destroy$)).subscribe(() => this._loadHistory());
  }

  private _loadHistory(): void {
    this.api.getSwitchHistory(30).subscribe(h => this.switchHistory.set(h as SwitchRecord[]));
  }

  getCameraById(id: string) {
    return this.store.cameras().find(c => c.id === id);
  }

  getCameraLabel(id: string | null): string {
    if (!id) return '—';
    return this.store.cameras().find(c => c.id === id)?.label ?? id;
  }

  ngOnDestroy(): void {
    this.destroy$.next();
    this.destroy$.complete();
  }
}
