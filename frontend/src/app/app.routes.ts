import { Routes } from '@angular/router';

export const routes: Routes = [
  {
    path: '',
    redirectTo: 'dashboard',
    pathMatch: 'full',
  },
  {
    path: 'dashboard',
    loadComponent: () =>
      import('./features/dashboard/dashboard.component').then(m => m.DashboardComponent),
  },
  {
    path: 'cameras',
    loadComponent: () =>
      import('./features/cameras/cameras.component').then(m => m.CamerasComponent),
  },
  {
    path: 'rules',
    loadComponent: () =>
      import('./features/rules/rules.component').then(m => m.RulesComponent),
  },
  {
    path: 'events',
    loadComponent: () =>
      import('./features/events/events.component').then(m => m.EventsComponent),
  },
  {
    path: 'monitoring',
    loadComponent: () =>
      import('./features/monitoring/monitoring.component').then(m => m.MonitoringComponent),
  },
  {
    path: 'obs',
    loadComponent: () =>
      import('./features/obs/obs.component').then(m => m.ObsComponent),
  },
  {
    path: 'settings',
    loadComponent: () =>
      import('./features/settings/settings.component').then(m => m.SettingsComponent),
  },
];
