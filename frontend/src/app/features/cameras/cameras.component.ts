import { Component, OnInit, signal, computed } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule, ReactiveFormsModule, FormBuilder, FormGroup, Validators, FormArray } from '@angular/forms';

import { TableModule } from 'primeng/table';
import { ButtonModule } from 'primeng/button';
import { DialogModule } from 'primeng/dialog';
import { InputTextModule } from 'primeng/inputtext';
import { DropdownModule } from 'primeng/dropdown';
import { InputSwitchModule } from 'primeng/inputswitch';
import { TagModule } from 'primeng/tag';
import { BadgeModule } from 'primeng/badge';
import { AccordionModule } from 'primeng/accordion';
import { SliderModule } from 'primeng/slider';
import { TooltipModule } from 'primeng/tooltip';
import { MessageService } from 'primeng/api';
import { ToastModule } from 'primeng/toast';

import { ApiService, Camera, CameraSubscription } from '../../core/api.service';
import { AppStore } from '../../store/app.store';

const REACTION_MODES = [
  { label: 'INFORM ONLY', value: 'INFORM_ONLY', severity: 'secondary' },
  { label: 'PREPARE', value: 'PREPARE', severity: 'info' },
  { label: 'SWITCH IF HIGH SCORE', value: 'SWITCH_IF_HIGH_SCORE', severity: 'warning' },
  { label: 'FORCE SWITCH', value: 'FORCE_SWITCH', severity: 'danger' },
];

const EVENT_TYPES = [
  'MATCH_START', 'MATCH_END', 'ATHLETE_READY', 'ATHLETE_POSITION',
  'SHOT_FIRED', 'ARROW_RECOVERY', 'TARGET_VALIDATION',
  'PENALTY', 'TIMEOUT', 'REFEREE_ANNOUNCEMENT',
];

@Component({
  selector: 'app-cameras',
  standalone: true,
  imports: [
    CommonModule, FormsModule, ReactiveFormsModule,
    TableModule, ButtonModule, DialogModule, InputTextModule,
    DropdownModule, InputSwitchModule, TagModule, BadgeModule,
    AccordionModule, SliderModule, TooltipModule, ToastModule,
  ],
  providers: [MessageService],
  template: `
    <div class="cameras-page">
      <div class="page-header">
        <div>
          <h1 class="page-title"><i class="pi pi-camera"></i> Camera Management</h1>
          <p class="page-subtitle">Configure cameras, sources, and event subscriptions</p>
        </div>
        <p-button icon="pi pi-plus" label="Add Camera" (onClick)="openCreateDialog()" />
      </div>

      <!-- Camera list -->
      <p-table [value]="cameras()" [rowHover]="true" styleClass="svs-table">
        <ng-template pTemplate="header">
          <tr>
            <th>Label</th>
            <th>Name</th>
            <th>Source</th>
            <th>Subscriptions</th>
            <th>Status</th>
            <th>Actions</th>
          </tr>
        </ng-template>
        <ng-template pTemplate="body" let-cam>
          <tr>
            <td>
              <div class="cam-label-cell">
                <span class="status-dot" [class.active]="cam.is_active"></span>
                <strong>{{ cam.label }}</strong>
              </div>
            </td>
            <td><span class="svs-monospace text-sm">{{ cam.name }}</span></td>
            <td>
              <p-tag [value]="cam.source_type.toUpperCase()" severity="info" />
              <div class="text-xs text-muted mt-1">{{ cam.source_url || cam.obs_scene_name || '—' }}</div>
            </td>
            <td>
              <div class="sub-chips">
                @for (sub of cam.subscriptions; track sub.event_type) {
                  <span class="sub-chip" [class]="'mode-' + sub.mode.toLowerCase()">
                    {{ sub.event_type }}
                  </span>
                }
                @if (cam.subscriptions.length === 0) {
                  <span class="text-muted text-xs">None</span>
                }
              </div>
            </td>
            <td>
              <p-tag [value]="cam.enabled ? 'ENABLED' : 'DISABLED'"
                     [severity]="cam.enabled ? 'success' : 'danger'" />
            </td>
            <td>
              <div class="action-btns">
                <p-button icon="pi pi-pencil" severity="secondary" [text]="true" size="small"
                          (onClick)="openEditDialog(cam)" pTooltip="Edit" />
                <p-button icon="pi pi-trash" severity="danger" [text]="true" size="small"
                          (onClick)="deleteCamera(cam.id)" pTooltip="Delete" />
              </div>
            </td>
          </tr>
        </ng-template>
        <ng-template pTemplate="emptymessage">
          <tr><td colspan="6" class="text-center p-4 text-muted">No cameras configured yet</td></tr>
        </ng-template>
      </p-table>

      <!-- Create/Edit dialog -->
      <p-dialog
        [(visible)]="dialogVisible"
        [header]="editingCamera ? 'Edit Camera' : 'Add Camera'"
        [modal]="true"
        [style]="{width: '680px'}"
        [draggable]="false"
      >
        <form [formGroup]="cameraForm" class="camera-form">

          <div class="form-row">
            <div class="form-field">
              <label>Label <span class="required">*</span></label>
              <input pInputText formControlName="label" placeholder="e.g. Target Cam 1" />
            </div>
            <div class="form-field">
              <label>Internal Name <span class="required">*</span></label>
              <input pInputText formControlName="name" placeholder="e.g. TARGET_CAM_1" />
            </div>
          </div>

          <div class="form-row">
            <div class="form-field">
              <label>Source Type</label>
              <p-dropdown formControlName="source_type" [options]="sourceTypes" optionLabel="label" optionValue="value" />
            </div>
            <div class="form-field">
              <label>Source URL / Scene Name</label>
              <input pInputText formControlName="source_url" placeholder="rtsp://... or OBS scene name" />
            </div>
          </div>

          <div class="form-field">
            <div class="switch-row">
              <p-inputSwitch formControlName="enabled" />
              <span>Enabled</span>
            </div>
          </div>

          <!-- Subscriptions -->
          <div class="section-divider">Event Subscriptions</div>

          <div formArrayName="subscriptions" class="subscriptions-list">
            @for (sub of subscriptionsArray.controls; track i; let i = $index) {
              <div [formGroupName]="i" class="subscription-row">
                <p-dropdown
                  formControlName="event_type"
                  [options]="eventTypeOptions"
                  placeholder="Event Type"
                  class="sub-event-select"
                />
                <p-dropdown
                  formControlName="mode"
                  [options]="modeOptions"
                  optionLabel="label"
                  optionValue="value"
                  class="sub-mode-select"
                />
                <div class="sub-priority">
                  <label class="text-xs">Priority: {{ sub.get('priority')?.value }}</label>
                  <p-slider formControlName="priority" [min]="0" [max]="100" />
                </div>
                <p-inputSwitch formControlName="enabled" pTooltip="Enable subscription" />
                <p-button icon="pi pi-trash" severity="danger" [text]="true" size="small"
                          (onClick)="removeSubscription(i)" />
              </div>
            }
          </div>

          <p-button
            icon="pi pi-plus"
            label="Add Subscription"
            severity="secondary"
            size="small"
            [text]="true"
            (onClick)="addSubscription()"
          />
        </form>

        <ng-template pTemplate="footer">
          <p-button label="Cancel" severity="secondary" (onClick)="closeDialog()" />
          <p-button
            [label]="editingCamera ? 'Update' : 'Create'"
            [loading]="saving()"
            (onClick)="saveCamera()"
          />
        </ng-template>
      </p-dialog>
    </div>
    <p-toast />
  `,
  styles: [`
    .cameras-page { padding: 1.5rem; height: 100%; overflow-y: auto; }

    .page-header {
      display: flex; justify-content: space-between; align-items: flex-start;
      margin-bottom: 1.5rem;
    }
    .page-title {
      margin: 0; font-size: 1.2rem; font-weight: 700;
      display: flex; align-items: center; gap: 0.5rem;
      i { color: var(--svs-accent); }
    }
    .page-subtitle { margin: 0.25rem 0 0; color: var(--svs-text-secondary); font-size: 0.82rem; }

    .cam-label-cell { display: flex; align-items: center; gap: 0.5rem; }
    .status-dot {
      width: 7px; height: 7px; border-radius: 50%; background: var(--svs-text-muted);
      &.active { background: var(--svs-success); animation: pulse-red 2s infinite; }
    }

    .sub-chips { display: flex; flex-wrap: wrap; gap: 3px; }
    .sub-chip {
      font-size: 0.62rem; padding: 2px 5px; border-radius: 3px; font-weight: 600;
      background: var(--svs-bg-elevated); color: var(--svs-text-secondary);
      &.mode-force_switch    { background: rgba(239,68,68,0.2); color: #ef9a9a; }
      &.mode-switch_if_high_score { background: rgba(245,158,11,0.2); color: #fbbf24; }
      &.mode-prepare         { background: rgba(59,130,246,0.2); color: #93c5fd; }
    }

    .action-btns { display: flex; gap: 4px; }

    .camera-form { display: flex; flex-direction: column; gap: 1rem; padding: 0.5rem 0; }
    .form-row { display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; }
    .form-field { display: flex; flex-direction: column; gap: 0.35rem; }
    .form-field label { font-size: 0.78rem; color: var(--svs-text-secondary); font-weight: 500; }
    .required { color: var(--svs-danger); }
    .switch-row { display: flex; align-items: center; gap: 0.5rem; font-size: 0.82rem; }

    .section-divider {
      font-size: 0.72rem; font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase;
      color: var(--svs-text-muted); border-bottom: 1px solid var(--svs-border); padding-bottom: 0.4rem;
    }

    .subscriptions-list { display: flex; flex-direction: column; gap: 0.5rem; }
    .subscription-row {
      display: grid; grid-template-columns: 1fr 1fr 1fr auto auto; gap: 0.5rem;
      align-items: center; padding: 0.5rem; background: var(--svs-bg-elevated);
      border-radius: var(--svs-radius-sm); border: 1px solid var(--svs-border);
    }
    .sub-priority { display: flex; flex-direction: column; gap: 4px; }
    .text-xs { font-size: 0.72rem; }
    .text-sm { font-size: 0.8rem; }
    .text-muted { color: var(--svs-text-muted); }
    .mt-1 { margin-top: 2px; }
    .text-center { text-align: center; }

    :host ::ng-deep .svs-table { background: var(--svs-bg-card); }
    :host ::ng-deep .sub-event-select .p-dropdown { width: 100%; }
    :host ::ng-deep .sub-mode-select .p-dropdown { width: 100%; }
  `],
})
export class CamerasComponent implements OnInit {
  cameras = signal<Camera[]>([]);
  dialogVisible = false;
  editingCamera: Camera | null = null;
  saving = signal(false);

  cameraForm!: FormGroup;

  sourceTypes = [
    { label: 'RTSP', value: 'rtsp' },
    { label: 'Webcam', value: 'webcam' },
    { label: 'NDI', value: 'ndi' },
    { label: 'OBS Scene', value: 'obs_scene' },
    { label: 'Mock (Testing)', value: 'mock' },
  ];

  modeOptions = REACTION_MODES;
  eventTypeOptions = EVENT_TYPES.map(t => ({ label: t, value: t }));

  constructor(
    private api: ApiService,
    private fb: FormBuilder,
    private msg: MessageService,
    public store: AppStore,
  ) {}

  ngOnInit(): void {
    this._initForm();
    this.loadCameras();
  }

  private _initForm(camera?: Camera): void {
    this.cameraForm = this.fb.group({
      name: [camera?.name ?? '', Validators.required],
      label: [camera?.label ?? '', Validators.required],
      source_type: [camera?.source_type ?? 'rtsp'],
      source_url: [camera?.source_url ?? ''],
      enabled: [camera?.enabled ?? true],
      subscriptions: this.fb.array(
        (camera?.subscriptions ?? []).map(s => this._subGroup(s))
      ),
    });
  }

  private _subGroup(sub?: Partial<CameraSubscription>) {
    return this.fb.group({
      event_type: [sub?.event_type ?? 'SHOT_FIRED'],
      mode: [sub?.mode ?? 'INFORM_ONLY'],
      priority: [sub?.priority ?? 50],
      duration_ms: [sub?.duration_ms ?? 3000],
      cooldown_ms: [sub?.cooldown_ms ?? 0],
      delay_ms: [sub?.delay_ms ?? 0],
      enabled: [sub?.enabled ?? true],
    });
  }

  get subscriptionsArray(): FormArray {
    return this.cameraForm.get('subscriptions') as FormArray;
  }

  addSubscription(): void {
    this.subscriptionsArray.push(this._subGroup());
  }

  removeSubscription(i: number): void {
    this.subscriptionsArray.removeAt(i);
  }

  loadCameras(): void {
    this.api.getCameras().subscribe(cams => {
      this.cameras.set(cams);
      this.store.setCameras(cams);
    });
  }

  openCreateDialog(): void {
    this.editingCamera = null;
    this._initForm();
    this.dialogVisible = true;
  }

  openEditDialog(camera: Camera): void {
    this.editingCamera = camera;
    this._initForm(camera);
    this.dialogVisible = true;
  }

  closeDialog(): void {
    this.dialogVisible = false;
  }

  saveCamera(): void {
    if (this.cameraForm.invalid) return;
    this.saving.set(true);
    const payload = this.cameraForm.value;

    const obs = this.editingCamera
      ? this.api.updateCamera(this.editingCamera.id, payload)
      : this.api.createCamera(payload);

    obs.subscribe({
      next: () => {
        this.msg.add({ severity: 'success', summary: 'Saved', detail: 'Camera saved successfully' });
        this.closeDialog();
        this.loadCameras();
        this.saving.set(false);
      },
      error: err => {
        this.msg.add({ severity: 'error', summary: 'Error', detail: err.message });
        this.saving.set(false);
      },
    });
  }

  deleteCamera(id: string): void {
    this.api.deleteCamera(id).subscribe(() => {
      this.msg.add({ severity: 'success', summary: 'Deleted', detail: 'Camera removed' });
      this.loadCameras();
    });
  }
}
