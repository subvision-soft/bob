import { Component, OnInit, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';

import { InputTextModule } from 'primeng/inputtext';
import { ButtonModule } from 'primeng/button';
import { InputSwitchModule } from 'primeng/inputswitch';
import { SliderModule } from 'primeng/slider';
import { TagModule } from 'primeng/tag';
import { ToastModule } from 'primeng/toast';
import { AccordionModule } from 'primeng/accordion';
import { MessageService } from 'primeng/api';

import { ApiService } from '../../core/api.service';

interface SystemSettings {
  external_api_url: string;
  poll_interval_ms: number;
  obs_url: string;
  obs_password: string;
  decision_cycle_ms: number;
  min_display_ms: number;
  default_cooldown_ms: number;
  score_threshold: number;
  snapshot_interval_ms: number;
  obs_enabled: boolean;
  debug: boolean;
}

@Component({
  selector: 'app-settings',
  standalone: true,
  imports: [
    CommonModule, FormsModule,
    InputTextModule, ButtonModule, InputSwitchModule,
    SliderModule, TagModule, ToastModule, AccordionModule,
  ],
  providers: [MessageService],
  template: `
    <div class="settings-page">

      <div class="page-header">
        <h1 class="page-title"><i class="pi pi-cog"></i> System Settings</h1>
        <p class="page-sub">Configure the Subvision Studio engine. Changes take effect after restart.</p>
      </div>

      <p-accordion [multiple]="true" [activeIndex]="[0,1,2]">

        <!-- External API -->
        <p-accordionTab>
          <ng-template pTemplate="header">
            <span class="tab-header"><i class="pi pi-cloud"></i> External Competition API</span>
          </ng-template>
          <div class="settings-grid">
            <div class="setting-row">
              <div class="setting-info">
                <label>API Base URL</label>
                <span>HTTP endpoint of the external competition event API</span>
              </div>
              <input pInputText [(ngModel)]="settings.external_api_url" (change)="onSettingChange()"
                     placeholder="http://localhost:9000/api" class="setting-input" />
            </div>
            <div class="setting-row">
              <div class="setting-info">
                <label>Polling Interval</label>
                <span>How often to check for new events (ms). Lower = faster reaction, higher = less load.</span>
              </div>
              <div class="slider-field">
                <p-slider [(ngModel)]="settings.poll_interval_ms" (change)="onSettingChange()" [min]="50" [max]="1000" [step]="50" />
                <span class="slider-val">{{ settings.poll_interval_ms }}ms</span>
              </div>
            </div>
          </div>
        </p-accordionTab>

        <!-- Realization Engine -->
        <p-accordionTab>
          <ng-template pTemplate="header">
            <span class="tab-header"><i class="pi pi-cpu"></i> Realization Engine</span>
          </ng-template>
          <div class="settings-grid">
            <div class="setting-row">
              <div class="setting-info">
                <label>Decision Cycle</label>
                <span>How often the decision engine evaluates camera scores (ms). Default: 50ms.</span>
              </div>
              <div class="slider-field">
               <p-slider [(ngModel)]="settings.decision_cycle_ms" (change)="onSettingChange()" [min]="20" [max]="500" [step]="10" />
                <span class="slider-val">{{ settings.decision_cycle_ms }}ms</span>
              </div>
            </div>
            <div class="setting-row">
              <div class="setting-info">
                <label>Minimum Display Duration</label>
                <span>Minimum time a camera must stay on air before switching (anti-zap). Default: 2000ms.</span>
              </div>
              <div class="slider-field">
                <p-slider [(ngModel)]="settings.min_display_ms" (change)="onSettingChange()" [min]="500" [max]="10000" [step]="500" />
                <span class="slider-val">{{ settings.min_display_ms }}ms</span>
              </div>
            </div>
            <div class="setting-row">
              <div class="setting-info">
                <label>Default Cooldown</label>
                <span>Post-switch cooldown applied to the switched-from camera. Default: 3000ms.</span>
              </div>
              <div class="slider-field">
                <p-slider [(ngModel)]="settings.default_cooldown_ms" (change)="onSettingChange()" [min]="0" [max]="10000" [step]="500" />
                <span class="slider-val">{{ settings.default_cooldown_ms }}ms</span>
              </div>
            </div>
            <div class="setting-row">
              <div class="setting-info">
                <label>Score Threshold (SWITCH_IF_HIGH_SCORE)</label>
                <span>Minimum interest score required to trigger a non-forced switch. Default: 60.</span>
              </div>
              <div class="slider-field">
                <p-slider [(ngModel)]="settings.score_threshold" (change)="onSettingChange()" [min]="0" [max]="100" [step]="5" />
                <span class="slider-val">{{ settings.score_threshold }}</span>
              </div>
            </div>
          </div>
        </p-accordionTab>

        <!-- OBS -->
        <p-accordionTab>
          <ng-template pTemplate="header">
            <span class="tab-header"><i class="pi pi-desktop"></i> OBS Integration</span>
          </ng-template>
          <div class="settings-grid">
            <div class="setting-row">
              <div class="setting-info">
                <label>Enable OBS Integration</label>
                <span>Toggle automatic OBS scene switching.</span>
              </div>
              <p-inputSwitch [(ngModel)]="settings.obs_enabled" (change)="onSettingChange()" />
            </div>
            <div class="setting-row">
              <div class="setting-info">
                <label>OBS WebSocket URL</label>
                <span>obs-websocket v5 endpoint. Default: ws://localhost:4455</span>
              </div>
              <input pInputText [(ngModel)]="settings.obs_url" (change)="onSettingChange()"
                     placeholder="ws://localhost:4455" class="setting-input" />
            </div>
            <div class="setting-row">
              <div class="setting-info">
                <label>OBS Password</label>
                <span>Leave blank if no password is set in OBS.</span>
              </div>
              <input pInputText type="password" [(ngModel)]="settings.obs_password" (change)="onSettingChange()"
                     placeholder="(blank = no password)" class="setting-input" />
            </div>
          </div>
        </p-accordionTab>

        <!-- Video -->
        <p-accordionTab>
          <ng-template pTemplate="header">
            <span class="tab-header"><i class="pi pi-video"></i> Video &amp; Streaming</span>
          </ng-template>
          <div class="settings-grid">
            <div class="setting-row">
              <div class="setting-info">
                <label>Snapshot Interval</label>
                <span>How often camera JPEG previews are pushed to the browser (ms). Default: 500ms.</span>
              </div>
              <div class="slider-field">
                <p-slider [(ngModel)]="settings.snapshot_interval_ms" (change)="onSettingChange()" [min]="100" [max]="2000" [step]="100" />
                <span class="slider-val">{{ settings.snapshot_interval_ms }}ms</span>
              </div>
            </div>
          </div>
        </p-accordionTab>

        <!-- Debug -->
        <p-accordionTab>
          <ng-template pTemplate="header">
            <span class="tab-header"><i class="pi pi-bug"></i> Debug</span>
          </ng-template>
          <div class="settings-grid">
            <div class="setting-row">
              <div class="setting-info">
                <label>Debug Mode</label>
                <span>Enable verbose logging and SQLAlchemy query logging.</span>
              </div>
              <p-inputSwitch [(ngModel)]="settings.debug" (change)="onSettingChange()" />
            </div>
            <div class="setting-row">
              <div class="setting-info">
                <label>Export Full Config</label>
                <span>Download a JSON export of all cameras, subscriptions and profiles.</span>
              </div>
              <p-button icon="pi pi-download" label="Export Config" severity="secondary"
                        size="small" (onClick)="exportConfig()" />
            </div>
          </div>
        </p-accordionTab>


      </p-accordion>

      <!-- Action buttons -->
      <div class="action-buttons">
        <p-button label="Save Settings" icon="pi pi-save" [loading]="saving()" [disabled]="!hasChanges()"
                  (onClick)="saveSettings()" />
        <p-button label="Reset Changes" icon="pi pi-undo" severity="secondary" [disabled]="!hasChanges()"
                  (onClick)="resetSettings()" />
      </div>

      <!-- Save notice -->
      <div class="save-notice">
        <i class="pi pi-info-circle"></i>
        <span>Settings are now saved to the database. Some settings (OBS URL, decision cycle, etc.) take effect immediately. Others may require a backend restart.</span>
      </div>

    </div>
    <p-toast />
  `,
  styles: [`
    .settings-page { padding: 1.5rem; height: 100%; overflow-y: auto; display: flex; flex-direction: column; gap: 1rem; }

    .page-header { margin-bottom: 0.25rem; }
    .page-title { margin: 0; font-size: 1.1rem; font-weight: 700; display: flex; align-items: center; gap: 0.5rem; i { color: var(--svs-accent); } }
    .page-sub { margin: 0.25rem 0 0; color: var(--svs-text-secondary); font-size: 0.8rem; }

    .tab-header { display: flex; align-items: center; gap: 0.5rem; font-size: 0.82rem; font-weight: 600; }

    .settings-grid { display: flex; flex-direction: column; gap: 0; }

    .setting-row {
      display: flex; align-items: center; justify-content: space-between; gap: 2rem;
      padding: 0.75rem 0; border-bottom: 1px solid var(--svs-border-subtle);
      &:last-child { border-bottom: none; }
    }
    .setting-info {
      flex: 1;
      label { display: block; font-size: 0.82rem; font-weight: 600; color: var(--svs-text-primary); margin-bottom: 2px; }
      span { font-size: 0.73rem; color: var(--svs-text-secondary); }
    }
    .setting-input { width: 280px; }
    .slider-field { display: flex; align-items: center; gap: 1rem; width: 280px; }
    .slider-val { font-family: var(--svs-font-mono); font-size: 0.82rem; color: var(--svs-accent); min-width: 60px; text-align: right; }

    :host ::ng-deep .p-slider { flex: 1; }
    :host ::ng-deep .p-accordion-header-link { background: var(--svs-bg-elevated) !important; border-color: var(--svs-border) !important; }
    :host ::ng-deep .p-accordion-content { background: var(--svs-bg-card) !important; border-color: var(--svs-border) !important; }

    .action-buttons {
      display: flex; gap: 0.5rem; margin-top: 1.5rem; padding-bottom: 1rem; border-bottom: 1px solid var(--svs-border);
    }

    .save-notice {
      display: flex; align-items: center; gap: 0.5rem;
      background: rgba(34,197,94,0.08); border: 1px solid rgba(34,197,94,0.3);
      border-radius: var(--svs-radius-sm); padding: 0.6rem 1rem; font-size: 0.78rem;
      color: var(--svs-text-secondary);
      i { color: var(--svs-success); }
      code { font-family: var(--svs-font-mono); color: var(--svs-text-primary); }
    }
  `],
})
export class SettingsComponent implements OnInit {
  settings: SystemSettings = {
    external_api_url: 'http://localhost:9000/api',
    poll_interval_ms: 100,
    obs_url: 'ws://localhost:4455',
    obs_password: '',
    decision_cycle_ms: 50,
    min_display_ms: 2000,
    default_cooldown_ms: 3000,
    score_threshold: 60,
    snapshot_interval_ms: 500,
    obs_enabled: true,
    debug: false,
  };

  originalSettings: SystemSettings = { ...this.settings };
  saving = signal(false);
  hasChanges = signal(false);

  constructor(
    private api: ApiService,
    private msg: MessageService,
  ) { }

  ngOnInit(): void {
    this.loadSettings();
  }

  loadSettings(): void {
    this.api.getSettings().subscribe({
      next: (response) => {
        if (response.settings) {
          // Map backend field names to UI field names
          const backendSettings = response.settings as Record<string, unknown>;
          this.settings = {
            external_api_url: String(backendSettings['external_api_url'] || this.settings.external_api_url),
            poll_interval_ms: Number(backendSettings['external_api_poll_interval_ms'] || this.settings.poll_interval_ms),
            obs_url: String(backendSettings['obs_websocket_url'] || this.settings.obs_url),
            obs_password: String(backendSettings['obs_websocket_password'] || this.settings.obs_password),
            decision_cycle_ms: Number(backendSettings['decision_cycle_ms'] || this.settings.decision_cycle_ms),
            min_display_ms: Number(backendSettings['min_display_duration_ms'] || this.settings.min_display_ms),
            default_cooldown_ms: Number(backendSettings['default_cooldown_ms'] || this.settings.default_cooldown_ms),
            score_threshold: Number(backendSettings['score_threshold_switch'] || this.settings.score_threshold),
            snapshot_interval_ms: Number(backendSettings['video_snapshot_interval_ms'] || this.settings.snapshot_interval_ms),
            obs_enabled: Boolean(backendSettings['obs_enabled']) || this.settings.obs_enabled,
            debug: Boolean(backendSettings['debug']) || this.settings.debug,
          };
          this.originalSettings = { ...this.settings };
          this.hasChanges.set(false);
        }
      },
      error: (err) => {
        this.msg.add({ severity: 'error', summary: 'Load Failed', detail: 'Could not load settings from server' });
        console.error('Failed to load settings:', err);
      },
    });
  }

  saveSettings(): void {
    this.saving.set(true);

    // Map UI field names to backend field names
    const updates: Record<string, { value: unknown; value_type: string }> = {
      'external_api_url': { value: this.settings.external_api_url, value_type: 'string' },
      'external_api_poll_interval_ms': { value: this.settings.poll_interval_ms, value_type: 'int' },
      'obs_websocket_url': { value: this.settings.obs_url, value_type: 'string' },
      'obs_websocket_password': { value: this.settings.obs_password, value_type: 'string' },
      'decision_cycle_ms': { value: this.settings.decision_cycle_ms, value_type: 'int' },
      'min_display_duration_ms': { value: this.settings.min_display_ms, value_type: 'int' },
      'default_cooldown_ms': { value: this.settings.default_cooldown_ms, value_type: 'int' },
      'score_threshold_switch': { value: this.settings.score_threshold, value_type: 'float' },
      'video_snapshot_interval_ms': { value: this.settings.snapshot_interval_ms, value_type: 'int' },
      'obs_enabled': { value: this.settings.obs_enabled, value_type: 'bool' },
      'debug': { value: this.settings.debug, value_type: 'bool' },
    };

    this.api.updateSettings(updates).subscribe({
      next: () => {
        this.msg.add({ severity: 'success', summary: 'Saved', detail: 'Settings have been saved. Some changes may require backend restart.' });
        this.originalSettings = { ...this.settings };
        this.hasChanges.set(false);
        this.saving.set(false);
      },
      error: (err) => {
        this.msg.add({ severity: 'error', summary: 'Save Failed', detail: err.error?.detail || 'Could not save settings' });
        this.saving.set(false);
      },
    });
  }

  resetSettings(): void {
    this.settings = { ...this.originalSettings };
    this.hasChanges.set(false);
  }

  onSettingChange(): void {
    this.hasChanges.set(JSON.stringify(this.settings) !== JSON.stringify(this.originalSettings));
  }

  exportConfig(): void {
    this.api.exportConfig().subscribe(data => {
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `subvision-config-${new Date().toISOString().slice(0, 10)}.json`;
      a.click();
      URL.revokeObjectURL(url);
      this.msg.add({ severity: 'success', summary: 'Exported', detail: 'Configuration downloaded' });
    });
  }
}
