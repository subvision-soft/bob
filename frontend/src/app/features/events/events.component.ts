import { Component, OnInit, OnDestroy, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Subject, takeUntil } from 'rxjs';
import { FormsModule } from '@angular/forms';

import { TableModule } from 'primeng/table';
import { ButtonModule } from 'primeng/button';
import { TagModule } from 'primeng/tag';
import { DropdownModule } from 'primeng/dropdown';
import { ToastModule } from 'primeng/toast';
import { PanelModule } from 'primeng/panel';
import { SplitterModule } from 'primeng/splitter';
import { MessageService } from 'primeng/api';

import { ApiService, EventLogEntry } from '../../core/api.service';
import { AppStore } from '../../store/app.store';
import { WebSocketService } from '../../core/websocket.service';

@Component({
  selector: 'app-events',
  standalone: true,
  imports: [
    CommonModule, FormsModule,
    TableModule, ButtonModule, TagModule, DropdownModule,
    ToastModule, PanelModule, SplitterModule,
  ],
  providers: [MessageService],
  template: `
    <div class="events-page">
      <p-splitter [panelSizes]="[65, 35]" styleClass="h-full">

        <!-- LEFT: Event history -->
        <ng-template pTemplate>
          <div class="events-col">
            <div class="col-header">
              <div class="svs-section-title"><i class="pi pi-list"></i> EVENT LOG</div>
              <p-button icon="pi pi-refresh" [text]="true" size="small" (onClick)="loadEvents()" />
            </div>

            <p-table [value]="events()" [scrollable]="true" scrollHeight="flex"
                     [rowHover]="true" styleClass="event-table" [virtualScroll]="true">
              <ng-template pTemplate="header">
                <tr>
                  <th style="width: 90px">Severity</th>
                  <th>Event Type</th>
                  <th>Athlete</th>
                  <th>Lane</th>
                  <th style="width: 110px">Time</th>
                </tr>
              </ng-template>
              <ng-template pTemplate="body" let-evt>
                <tr class="event-row" [class]="'sev-' + evt.severity.toLowerCase()">
                  <td>
                    <p-tag [value]="evt.severity"
                           [severity]="getSeverityLevel(evt.severity)" />
                  </td>
                  <td><strong class="svs-monospace">{{ evt.event_type }}</strong></td>
                  <td><span class="text-muted">{{ evt.athlete_id ?? '—' }}</span></td>
                  <td><span class="text-muted">{{ evt.lane ?? '—' }}</span></td>
                  <td><span class="text-muted monospace-sm">{{ evt.received_at * 1000 | date:'HH:mm:ss.SSS' }}</span></td>
                </tr>
              </ng-template>
              <ng-template pTemplate="emptymessage">
                <tr><td colspan="5" class="empty-cell">No events recorded yet</td></tr>
              </ng-template>
            </p-table>
          </div>
        </ng-template>

        <!-- RIGHT: Event simulator -->
        <ng-template pTemplate>
          <div class="simulator-col">
            <div class="svs-section-title"><i class="pi pi-play"></i> EVENT SIMULATOR</div>
            <p class="sim-desc">Inject test events to verify your rules and camera subscriptions.</p>

            <div class="sim-grid">
              @for (evt of quickEvents; track evt.type) {
                <button class="sim-btn" [class]="'sim-btn--' + evt.severity.toLowerCase()"
                        (click)="simulate(evt.type)" [disabled]="simulating()">
                  <i [class]="'pi ' + evt.icon"></i>
                  <span class="sim-btn__type">{{ evt.type }}</span>
                  <span class="sim-btn__sev">{{ evt.severity }}</span>
                </button>
              }
            </div>

            <div class="section-divider">Custom Event</div>
            <div class="custom-sim">
              <p-dropdown
                [(ngModel)]="customEventType"
                [options]="eventTypeOptions"
                placeholder="Select event type"
                [style]="{width: '100%'}"
              />
              <p-button
                label="Simulate"
                icon="pi pi-bolt"
                [loading]="simulating()"
                (onClick)="simulate(customEventType)"
                [disabled]="!customEventType"
              />
            </div>

            @if (lastSimulated()) {
              <div class="sim-result">
                <i class="pi pi-check-circle"></i>
                Simulated: <strong>{{ lastSimulated() }}</strong>
              </div>
            }
          </div>
        </ng-template>
      </p-splitter>
    </div>
    <p-toast />
  `,
  styles: [`
    .events-page { height: 100%; display: flex; flex-direction: column; overflow: hidden; }
    :host ::ng-deep .p-splitter { height: 100% !important; }

    .events-col { display: flex; flex-direction: column; height: 100%; overflow: hidden; }
    .col-header { display: flex; justify-content: space-between; align-items: center; }

    .event-row { font-size: 0.78rem; }
    .event-row.sev-critical { background: rgba(239,68,68,0.04) !important; }
    .event-row.sev-high     { background: rgba(249,115,22,0.04) !important; }

    .empty-cell { text-align: center; padding: 2rem; color: var(--svs-text-muted); }
    .text-muted { color: var(--svs-text-muted); }
    .monospace-sm { font-family: var(--svs-font-mono); font-size: 0.7rem; }

    /* Simulator */
    .simulator-col { padding: 8px; display: flex; flex-direction: column; gap: 0.75rem; }
    .sim-desc { margin: 0; font-size: 0.78rem; color: var(--svs-text-secondary); }

    .sim-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; }
    .sim-btn {
      display: flex; flex-direction: column; align-items: flex-start; gap: 2px;
      padding: 8px 10px; border-radius: var(--svs-radius-sm);
      background: var(--svs-bg-elevated); border: 1px solid var(--svs-border);
      cursor: pointer; transition: background 0.15s, border-color 0.15s; text-align: left;

      &:hover { background: var(--svs-bg-card); border-color: var(--svs-accent); }
      &:disabled { opacity: 0.5; cursor: not-allowed; }
      &--critical { border-left: 3px solid var(--svs-danger); }
      &--high     { border-left: 3px solid var(--svs-critical); }
      &--medium   { border-left: 3px solid var(--svs-accent); }
      &--low      { border-left: 3px solid var(--svs-border); }
    }
    .sim-btn__type { font-size: 0.72rem; font-weight: 600; color: var(--svs-text-primary); font-family: var(--svs-font-mono); }
    .sim-btn__sev  { font-size: 0.6rem; color: var(--svs-text-muted); text-transform: uppercase; }

    .section-divider {
      font-size: 0.7rem; font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase;
      color: var(--svs-text-muted); border-bottom: 1px solid var(--svs-border); padding-bottom: 4px;
    }
    .custom-sim { display: flex; flex-direction: column; gap: 0.5rem; }

    .sim-result {
      display: flex; align-items: center; gap: 0.5rem;
      background: rgba(34,197,94,0.1); border: 1px solid rgba(34,197,94,0.3);
      border-radius: 4px; padding: 6px 10px; font-size: 0.78rem; color: var(--svs-success);
      animation: slide-in-right 0.2s ease;
    }
  `],
})
export class EventsComponent implements OnInit, OnDestroy {
  private destroy$ = new Subject<void>();

  events = signal<EventLogEntry[]>([]);
  simulating = signal(false);
  lastSimulated = signal<string | null>(null);
  customEventType = '';

  eventTypeOptions = [
    'MATCH_START', 'MATCH_END', 'ATHLETE_READY', 'ATHLETE_POSITION',
    'SHOT_FIRED', 'ARROW_RECOVERY', 'TARGET_VALIDATION',
    'PENALTY', 'TIMEOUT', 'REFEREE_ANNOUNCEMENT',
  ].map(t => ({ label: t, value: t }));

  quickEvents = [
    { type: 'SHOT_FIRED', severity: 'CRITICAL', icon: 'pi-bullseye' },
    { type: 'TARGET_VALIDATION', severity: 'HIGH', icon: 'pi-check-circle' },
    { type: 'MATCH_START', severity: 'HIGH', icon: 'pi-play' },
    { type: 'MATCH_END', severity: 'HIGH', icon: 'pi-stop' },
    { type: 'ARROW_RECOVERY', severity: 'MEDIUM', icon: 'pi-arrow-up' },
    { type: 'ATHLETE_READY', severity: 'MEDIUM', icon: 'pi-user' },
    { type: 'PENALTY', severity: 'HIGH', icon: 'pi-times-circle' },
    { type: 'TIMEOUT', severity: 'MEDIUM', icon: 'pi-pause' },
  ];

  constructor(
    private api: ApiService,
    private ws: WebSocketService,
    public store: AppStore,
    private msg: MessageService,
  ) {}

  ngOnInit(): void {
    this.loadEvents();

    // Subscribe to live events
    this.ws.on('event_received').pipe(takeUntil(this.destroy$)).subscribe(msg => {
      if (msg.data) {
        const ev = msg.data as EventLogEntry;
        this.events.update(evts => [ev, ...evts].slice(0, 500));
        this.store.pushEvent(ev);
      }
    });
  }

  loadEvents(): void {
    this.api.getEvents(200).subscribe(evts => this.events.set(evts));
  }

  simulate(eventType: string): void {
    if (!eventType) return;
    this.simulating.set(true);
    this.api.simulateEvent(eventType).subscribe({
      next: () => {
        this.lastSimulated.set(eventType);
        this.simulating.set(false);
        setTimeout(() => this.lastSimulated.set(null), 3000);
      },
      error: () => this.simulating.set(false),
    });
  }

  getSeverityLevel(severity: string): 'success' | 'info' | 'warning' | 'danger' | 'secondary' | undefined {
    const map: Record<string, 'success' | 'info' | 'warning' | 'danger' | 'secondary'> = {
      CRITICAL: 'danger',
      HIGH: 'warning',
      MEDIUM: 'info',
      LOW: 'secondary',
    };
    return map[severity];
  }

  ngOnDestroy(): void {
    this.destroy$.next();
    this.destroy$.complete();
  }
}
