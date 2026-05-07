import { Component, OnInit, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule, ReactiveFormsModule, FormBuilder, FormGroup, Validators } from '@angular/forms';

import { TableModule } from 'primeng/table';
import { ButtonModule } from 'primeng/button';
import { DialogModule } from 'primeng/dialog';
import { InputTextModule } from 'primeng/inputtext';
import { TagModule } from 'primeng/tag';
import { InputSwitchModule } from 'primeng/inputswitch';
import { ToastModule } from 'primeng/toast';
import { AccordionModule } from 'primeng/accordion';
import { InputTextareaModule } from 'primeng/inputtextarea';
import { MessageService } from 'primeng/api';

import { ApiService, RuleProfile } from '../../core/api.service';

@Component({
  selector: 'app-rules',
  standalone: true,
  imports: [
    CommonModule, FormsModule, ReactiveFormsModule,
    TableModule, ButtonModule, DialogModule, InputTextModule,
    TagModule, InputSwitchModule, ToastModule, AccordionModule, InputTextareaModule,
  ],
  providers: [MessageService],
  template: `
    <div class="rules-page">

      <div class="page-header">
        <div>
          <h1 class="page-title"><i class="pi pi-sliders-h"></i> Rule Profiles</h1>
          <p class="page-sub">Manage realization profiles. Each profile can override engine parameters and serve as a template.</p>
        </div>
        <p-button icon="pi pi-plus" label="New Profile" (onClick)="openCreate()" />
      </div>

      <!-- Info banner -->
      <div class="info-banner">
        <i class="pi pi-info-circle"></i>
        <span>
          Camera-level event subscriptions are configured in the <strong>Cameras</strong> section.
          Rule profiles allow you to group settings and switch between competition configurations.
        </span>
      </div>

      <!-- Profile list -->
      <div class="profile-grid">
        @for (profile of profiles(); track profile.id) {
          <div class="profile-card" [class.active]="profile.is_active">
            <div class="profile-card__header">
              <div class="profile-card__name">
                <span>{{ profile.name }}</span>
                @if (profile.is_active) {
                  <p-tag value="ACTIVE" severity="success" />
                }
              </div>
              <div class="profile-card__actions">
                <p-button icon="pi pi-play" pTooltip="Activate" severity="success" [text]="true" size="small"
                          (onClick)="activateProfile(profile.id)" [disabled]="profile.is_active" />
                <p-button icon="pi pi-trash" pTooltip="Delete" severity="danger" [text]="true" size="small"
                          (onClick)="deleteProfile(profile.id)" [disabled]="profile.is_active" />
              </div>
            </div>

            @if (profile.description) {
              <p class="profile-card__desc">{{ profile.description }}</p>
            }

            @if (profile.config && hasConfig(profile)) {
              <div class="profile-config">
                <div class="config-row" *ngIf="profile.config!['min_display_duration_ms']">
                  <span class="config-key">Min Display</span>
                  <span class="config-val">{{ profile.config!['min_display_duration_ms'] }}ms</span>
                </div>
                <div class="config-row" *ngIf="profile.config!['default_cooldown_ms']">
                  <span class="config-key">Cooldown</span>
                  <span class="config-val">{{ profile.config!['default_cooldown_ms'] }}ms</span>
                </div>
                <div class="config-row" *ngIf="profile.config!['score_threshold_switch']">
                  <span class="config-key">Score Threshold</span>
                  <span class="config-val">{{ profile.config!['score_threshold_switch'] }}</span>
                </div>
                <div class="config-row" *ngIf="profile.config!['decision_cycle_ms']">
                  <span class="config-key">Decision Cycle</span>
                  <span class="config-val">{{ profile.config!['decision_cycle_ms'] }}ms</span>
                </div>
              </div>
            }
          </div>
        }

        @if (profiles().length === 0) {
          <div class="empty-state">
            <i class="pi pi-sliders-h"></i>
            <p>No rule profiles yet. Create one to get started.</p>
          </div>
        }
      </div>

      <!-- How it works -->
      <div class="how-it-works svs-card">
        <div class="svs-section-title"><i class="pi pi-question-circle"></i> HOW THE RULE ENGINE WORKS</div>
        <div class="how-grid">
          <div class="how-step">
            <div class="how-step__num">1</div>
            <div class="how-step__body">
              <strong>External API → Event Engine</strong>
              <p>Events are polled every {{ pollInterval }}ms, deduplicated, and published to the global event bus.</p>
            </div>
          </div>
          <div class="how-step">
            <div class="how-step__num">2</div>
            <div class="how-step__body">
              <strong>Event Bus → Camera Subscribers</strong>
              <p>Every camera receives every event. Each matches against its configured subscriptions and updates its interest score.</p>
            </div>
          </div>
          <div class="how-step">
            <div class="how-step__num">3</div>
            <div class="how-step__body">
              <strong>Scoring Formula</strong>
              <code class="code-block">score = event_priority + activity_decay + critical_bonus − cooldown_penalty − repetition_penalty</code>
            </div>
          </div>
          <div class="how-step">
            <div class="how-step__num">4</div>
            <div class="how-step__body">
              <strong>Decision Engine → OBS</strong>
              <p>Every 50ms, the Decision Engine picks the highest-scoring camera and triggers the OBS scene switch if thresholds are met.</p>
            </div>
          </div>
        </div>

        <div class="mode-table">
          <div class="svs-section-title" style="margin-top: 0.75rem"><i class="pi pi-list"></i> REACTION MODES</div>
          @for (mode of reactionModes; track mode.name) {
            <div class="mode-row">
              <p-tag [value]="mode.name" [severity]="mode.severity" />
              <span class="mode-desc">{{ mode.desc }}</span>
            </div>
          }
        </div>
      </div>

      <!-- Create dialog -->
      <p-dialog [(visible)]="dialogVisible" header="New Rule Profile"
                [modal]="true" [style]="{width: '520px'}">
        <form [formGroup]="profileForm" class="profile-form">
          <div class="form-field">
            <label>Profile Name <span class="required">*</span></label>
            <input pInputText formControlName="name" placeholder="e.g. Championship Finals" />
          </div>
          <div class="form-field">
            <label>Description</label>
            <textarea pTextarea formControlName="description" rows="2"
                      placeholder="Optional description"></textarea>
          </div>

          <div class="section-divider">Engine Overrides (optional)</div>
          <p class="override-hint">Leave blank to use global settings from Settings page.</p>

          <div class="form-row">
            <div class="form-field">
              <label>Min Display (ms)</label>
              <input pInputText type="number" formControlName="min_display_duration_ms" placeholder="2000" />
            </div>
            <div class="form-field">
              <label>Cooldown (ms)</label>
              <input pInputText type="number" formControlName="default_cooldown_ms" placeholder="3000" />
            </div>
          </div>
          <div class="form-row">
            <div class="form-field">
              <label>Score Threshold</label>
              <input pInputText type="number" formControlName="score_threshold_switch" placeholder="60" />
            </div>
            <div class="form-field">
              <label>Decision Cycle (ms)</label>
              <input pInputText type="number" formControlName="decision_cycle_ms" placeholder="50" />
            </div>
          </div>
        </form>

        <ng-template pTemplate="footer">
          <p-button label="Cancel" severity="secondary" (onClick)="dialogVisible = false" />
          <p-button label="Create" [loading]="saving()" (onClick)="saveProfile()" />
        </ng-template>
      </p-dialog>

    </div>
    <p-toast />
  `,
  styles: [`
    .rules-page { padding: 1.5rem; height: 100%; overflow-y: auto; display: flex; flex-direction: column; gap: 1rem; }

    .page-header { display: flex; justify-content: space-between; align-items: flex-start; }
    .page-title { margin: 0; font-size: 1.1rem; font-weight: 700; display: flex; align-items: center; gap: 0.5rem; i { color: var(--svs-accent); } }
    .page-sub { margin: 0.25rem 0 0; color: var(--svs-text-secondary); font-size: 0.8rem; }

    .info-banner {
      display: flex; align-items: center; gap: 0.5rem;
      background: rgba(59,130,246,0.1); border: 1px solid rgba(59,130,246,0.3);
      border-radius: var(--svs-radius-sm); padding: 0.6rem 1rem; font-size: 0.8rem;
      color: var(--svs-text-secondary);
      i { color: var(--svs-accent); }
    }

    .profile-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 0.75rem; }

    .profile-card {
      background: var(--svs-bg-card); border: 1px solid var(--svs-border);
      border-radius: var(--svs-radius-md); padding: 0.75rem 1rem;
      transition: border-color 0.2s;
      &.active { border-color: var(--svs-success); }
    }
    .profile-card__header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px; }
    .profile-card__name { display: flex; align-items: center; gap: 0.5rem; font-weight: 600; font-size: 0.88rem; }
    .profile-card__actions { display: flex; gap: 2px; }
    .profile-card__desc { margin: 0; font-size: 0.75rem; color: var(--svs-text-secondary); }

    .profile-config { margin-top: 8px; display: flex; flex-direction: column; gap: 2px; }
    .config-row { display: flex; justify-content: space-between; font-size: 0.72rem; padding: 2px 0; border-bottom: 1px solid var(--svs-border-subtle); }
    .config-key { color: var(--svs-text-muted); }
    .config-val { color: var(--svs-accent); font-family: var(--svs-font-mono); }

    .how-it-works { padding: 0; overflow: hidden; }
    .how-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 1px; background: var(--svs-border); }
    .how-step {
      display: flex; align-items: flex-start; gap: 0.75rem;
      padding: 0.75rem 1rem; background: var(--svs-bg-card);
    }
    .how-step__num {
      width: 24px; height: 24px; border-radius: 50%; background: var(--svs-accent);
      color: #fff; display: flex; align-items: center; justify-content: center;
      font-size: 0.75rem; font-weight: 700; flex-shrink: 0;
    }
    .how-step__body strong { display: block; font-size: 0.8rem; margin-bottom: 4px; }
    .how-step__body p { margin: 0; font-size: 0.75rem; color: var(--svs-text-secondary); }
    .code-block {
      display: block; font-family: var(--svs-font-mono); font-size: 0.68rem;
      background: var(--svs-bg-elevated); padding: 6px 8px; border-radius: 4px; margin-top: 4px;
      color: var(--svs-success);
    }

    .mode-table { padding: 0 0.5rem 0.5rem; display: flex; flex-direction: column; gap: 4px; }
    .mode-row { display: flex; align-items: center; gap: 0.75rem; padding: 4px 6px; }
    .mode-desc { font-size: 0.75rem; color: var(--svs-text-secondary); }

    .profile-form { display: flex; flex-direction: column; gap: 0.75rem; padding: 0.5rem 0; }
    .form-row { display: grid; grid-template-columns: 1fr 1fr; gap: 0.75rem; }
    .form-field { display: flex; flex-direction: column; gap: 0.3rem; }
    .form-field label { font-size: 0.75rem; color: var(--svs-text-secondary); }
    .required { color: var(--svs-danger); }
    .section-divider { font-size: 0.7rem; font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase; color: var(--svs-text-muted); border-bottom: 1px solid var(--svs-border); padding-bottom: 4px; }
    .override-hint { margin: 0; font-size: 0.72rem; color: var(--svs-text-muted); }

    .empty-state { display: flex; flex-direction: column; align-items: center; gap: 0.5rem; padding: 2rem; color: var(--svs-text-muted); i { font-size: 1.5rem; } }
  `],
})
export class RulesComponent implements OnInit {
  profiles = signal<RuleProfile[]>([]);
  dialogVisible = false;
  saving = signal(false);
  pollInterval = 100;

  profileForm!: FormGroup;

  reactionModes: { name: string; severity: 'success' | 'info' | 'warning' | 'danger' | 'secondary'; desc: string }[] = [
    { name: 'INFORM_ONLY', severity: 'secondary', desc: 'Camera receives event for context only — no switch triggered.' },
    { name: 'PREPARE', severity: 'info', desc: 'Pre-loads OBS preview and warms PTZ — no immediate program switch.' },
    { name: 'SWITCH_IF_HIGH_SCORE', severity: 'warning', desc: 'Triggers switch only if camera score exceeds the configured threshold.' },
    { name: 'FORCE_SWITCH', severity: 'danger', desc: 'Absolute priority — bypasses cooldowns and score thresholds.' },
  ];

  constructor(
    private api: ApiService,
    private fb: FormBuilder,
    private msg: MessageService,
  ) {}

  ngOnInit(): void {
    this.loadProfiles();
    this._initForm();
  }

  private _initForm(): void {
    this.profileForm = this.fb.group({
      name: ['', Validators.required],
      description: [''],
      min_display_duration_ms: [null],
      default_cooldown_ms: [null],
      score_threshold_switch: [null],
      decision_cycle_ms: [null],
    });
  }

  loadProfiles(): void {
    this.api.getProfiles().subscribe(p => this.profiles.set(p));
  }

  openCreate(): void {
    this._initForm();
    this.dialogVisible = true;
  }

  saveProfile(): void {
    if (this.profileForm.invalid) return;
    this.saving.set(true);
    const v = this.profileForm.value;
    const config: Record<string, unknown> = {};
    if (v.min_display_duration_ms) config['min_display_duration_ms'] = +v.min_display_duration_ms;
    if (v.default_cooldown_ms) config['default_cooldown_ms'] = +v.default_cooldown_ms;
    if (v.score_threshold_switch) config['score_threshold_switch'] = +v.score_threshold_switch;
    if (v.decision_cycle_ms) config['decision_cycle_ms'] = +v.decision_cycle_ms;

    this.api.createProfile({ name: v.name, description: v.description, config }).subscribe({
      next: () => {
        this.msg.add({ severity: 'success', summary: 'Created', detail: 'Profile created' });
        this.dialogVisible = false;
        this.saving.set(false);
        this.loadProfiles();
      },
      error: err => {
        this.msg.add({ severity: 'error', summary: 'Error', detail: err.message });
        this.saving.set(false);
      },
    });
  }

  activateProfile(id: string): void {
    this.api.activateProfile(id).subscribe(() => {
      this.msg.add({ severity: 'success', summary: 'Activated', detail: 'Profile activated' });
      this.loadProfiles();
    });
  }

  deleteProfile(id: string): void {
    this.api.deleteProfile(id).subscribe(() => {
      this.msg.add({ severity: 'success', summary: 'Deleted', detail: 'Profile deleted' });
      this.loadProfiles();
    });
  }

  hasConfig(profile: RuleProfile): boolean {
    return profile.config !== null && Object.keys(profile.config ?? {}).length > 0;
  }
}
