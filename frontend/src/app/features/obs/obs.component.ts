import { Component, OnInit, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';

import { ButtonModule } from 'primeng/button';
import { InputTextModule } from 'primeng/inputtext';
import { PasswordModule } from 'primeng/password';
import { TagModule } from 'primeng/tag';
import { TableModule } from 'primeng/table';
import { ToastModule } from 'primeng/toast';
import { PanelModule } from 'primeng/panel';
import { MessageService } from 'primeng/api';

import { ApiService, OBSStatus } from '../../core/api.service';
import { AppStore } from '../../store/app.store';

@Component({
  selector: 'app-obs',
  standalone: true,
  imports: [
    CommonModule, FormsModule,
    ButtonModule, InputTextModule, PasswordModule,
    TagModule, TableModule, ToastModule, PanelModule,
  ],
  providers: [MessageService],
  template: `
    <div class="obs-page">

      <div class="page-header">
        <h1 class="page-title"><i class="pi pi-desktop"></i> OBS Integration</h1>
      </div>

      <!-- Connection card -->
      <div class="svs-card connection-card">
        <div class="connection-status">
          <div class="status-indicator" [class.connected]="isConnected()">
            <i class="pi" [class.pi-circle-fill]="isConnected()" [class.pi-circle]="!isConnected()"></i>
            <span class="status-text">{{ isConnected() ? 'Connected to OBS' : 'Not Connected' }}</span>
            @if (isConnected()) {
              <p-tag [value]="store.obsStatus()?.state ?? ''" severity="success" />
            }
          </div>
        </div>

        <div class="connection-form">
          <div class="form-field">
            <label>WebSocket URL</label>
            <input pInputText [(ngModel)]="obsUrl" placeholder="ws://localhost:4455" [disabled]="isConnected()" />
          </div>
          <div class="form-field">
            <label>Password</label>
            <p-password [(ngModel)]="obsPassword" [feedback]="false" [disabled]="isConnected()" />
          </div>
          <div class="conn-actions">
            @if (!isConnected()) {
              <p-button label="Connect" icon="pi pi-link" [loading]="connecting()" (onClick)="connect()" />
            } @else {
              <p-button label="Disconnect" icon="pi pi-times" severity="danger" (onClick)="disconnect()" />
              <p-button label="Refresh Scenes" icon="pi pi-refresh" severity="secondary" (onClick)="refreshStatus()" />
            }
          </div>
        </div>
      </div>

      <!-- Current state -->
      @if (isConnected() && store.obsStatus(); as status) {
        <div class="obs-state">
          <div class="state-card state-card--program">
            <div class="state-card__label">PROGRAM</div>
            <div class="state-card__value">{{ status.current_program ?? '—' }}</div>
          </div>
          <div class="state-card state-card--preview">
            <div class="state-card__label">PREVIEW</div>
            <div class="state-card__value">{{ status.current_preview ?? '—' }}</div>
          </div>
        </div>

        <!-- Scene list -->
        <div class="svs-card scenes-card">
          <div class="svs-section-title"><i class="pi pi-list"></i> SCENES</div>
          <div class="scene-list">
            @for (scene of status.scenes; track scene) {
              <div class="scene-item">
                <span class="scene-name">{{ scene }}</span>
                <div class="scene-actions">
                  <p-button
                    label="Program"
                    size="small"
                    severity="danger"
                    [outlined]="true"
                    (onClick)="setScene(scene, 'program')"
                  />
                  <p-button
                    label="Preview"
                    size="small"
                    severity="success"
                    [outlined]="true"
                    (onClick)="setScene(scene, 'preview')"
                  />
                </div>
              </div>
            }
          </div>
        </div>
      }

    </div>
    <p-toast />
  `,
  styles: [`
    .obs-page { padding: 1.5rem; height: 100%; overflow-y: auto; display: flex; flex-direction: column; gap: 1rem; }
    .page-header { margin-bottom: 0.5rem; }
    .page-title { margin: 0; font-size: 1.1rem; font-weight: 700; display: flex; align-items: center; gap: 0.5rem; i { color: var(--svs-accent); } }

    .connection-card { padding: 1rem; display: flex; flex-direction: column; gap: 1rem; }
    .connection-status { display: flex; align-items: center; }
    .status-indicator {
      display: flex; align-items: center; gap: 0.5rem; font-size: 0.85rem;
      i { color: var(--svs-text-muted); }
      &.connected i { color: var(--svs-success); }
    }
    .status-text { font-weight: 600; }

    .connection-form {
      display: grid; grid-template-columns: 1fr 1fr auto; gap: 0.75rem; align-items: end;
    }
    .form-field { display: flex; flex-direction: column; gap: 0.3rem; }
    .form-field label { font-size: 0.75rem; color: var(--svs-text-secondary); }
    .conn-actions { display: flex; gap: 0.5rem; }

    .obs-state { display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; }
    .state-card {
      background: var(--svs-bg-card); border: 2px solid var(--svs-border);
      border-radius: var(--svs-radius-md); padding: 0.75rem 1rem;
      &--program { border-color: var(--svs-program-color); }
      &--preview { border-color: var(--svs-preview-color); }
    }
    .state-card__label {
      font-size: 0.65rem; font-weight: 700; letter-spacing: 0.1em;
      color: var(--svs-text-muted); margin-bottom: 4px;
    }
    .state-card__value { font-size: 0.9rem; font-weight: 600; font-family: var(--svs-font-mono); }

    .scenes-card { padding: 0; overflow: hidden; }
    .scene-list { display: flex; flex-direction: column; }
    .scene-item {
      display: flex; justify-content: space-between; align-items: center;
      padding: 8px 12px; border-bottom: 1px solid var(--svs-border-subtle);
      &:last-child { border-bottom: none; }
      &:hover { background: var(--svs-bg-elevated); }
    }
    .scene-name { font-size: 0.82rem; font-family: var(--svs-font-mono); }
    .scene-actions { display: flex; gap: 0.4rem; }
  `],
})
export class ObsComponent implements OnInit {
  obsUrl = 'ws://localhost:4455';
  obsPassword = '';
  connecting = signal(false);

  constructor(
    private api: ApiService,
    public store: AppStore,
    private msg: MessageService,
  ) { }

  ngOnInit(): void {
    this.refreshStatus();
  }

  isConnected(): boolean {
    return this.store.obsStatus()?.state === 'CONNECTED';
  }

  connect(): void {
    this.connecting.set(true);
    this.api.connectObs(this.obsUrl, this.obsPassword).subscribe({
      next: () => {
        // Save connection settings to localStorage
        localStorage.setItem('obs_settings', JSON.stringify({
          url: this.obsUrl,
          password: this.obsPassword,
        }));
        this.msg.add({ severity: 'success', summary: 'Connected', detail: 'OBS connected successfully' });
        this.refreshStatus();
        this.connecting.set(false);
      },
      error: err => {
        this.msg.add({ severity: 'error', summary: 'Connection Failed', detail: err.error?.detail ?? err.message });
        this.connecting.set(false);
      },
    });
  }

  disconnect(): void {
    this.api.disconnectObs().subscribe(() => {
      this.msg.add({ severity: 'info', summary: 'Disconnected', detail: 'OBS disconnected' });
      this.refreshStatus();
    });
  }

  refreshStatus(): void {
    this.api.getObsStatus().subscribe(s => this.store.updateObsStatus(s));
  }

  setScene(scene: string, target: 'program' | 'preview'): void {
    this.api.setObsScene(scene, target).subscribe({
      next: () => {
        this.msg.add({ severity: 'success', summary: 'Scene Set', detail: `${scene} → ${target}` });
        // Refresh status to show updated scene
        setTimeout(() => this.refreshStatus(), 100);
      },
      error: err => this.msg.add({ severity: 'error', summary: 'Error', detail: err.message }),
    });
  }
}
