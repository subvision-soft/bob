/**
 * WebSocket Service — Real-time connection to Subvision Studio backend.
 * 
 * Uses RxJS WebSocketSubject with automatic reconnection.
 * Provides typed observable streams for each message type.
 */

import { Injectable, OnDestroy, signal, computed } from '@angular/core';
import { webSocket, WebSocketSubject } from 'rxjs/webSocket';
import {
  Subject, Observable, timer, EMPTY,
  catchError, distinctUntilChanged, filter, map,
  retry, share, switchMap, takeUntil, tap,
} from 'rxjs';

export type WsMessageType =
  | 'camera_scores'
  | 'event_received'
  | 'program_switch'
  | 'decision_trace'
  | 'event_received'
  | 'obs_state'
  | 'stream_health'
  | 'log'
  | 'global_context'
  | 'snapshot'
  | 'pong'
  | 'simulate_ack';

export interface WsMessage<T = unknown> {
  type: WsMessageType;
  data?: T;
  ts?: number;
  camera_id?: string;
}

function buildWsUrl(): string {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';

  // Angular dev server: backend is on 8000.
  if (window.location.port === '4200') {
    return `${protocol}//${window.location.hostname}:8000/ws`;
  }

  // Deployed (nginx/docker): use same host and proxy path /ws.
  return `${protocol}//${window.location.host}/ws`;
}

const WS_URL = buildWsUrl();
const RECONNECT_INTERVAL_MS = 3000;

@Injectable({ providedIn: 'root' })
export class WebSocketService implements OnDestroy {
  private readonly destroy$ = new Subject<void>();
  private socket$!: WebSocketSubject<WsMessage>;
  private messages$!: Observable<WsMessage>;

  // ── Connection state ───────────────────────────────────────────
  readonly isConnected = signal(false);
  readonly reconnectCount = signal(0);

  constructor() {
    this._connect();
  }

  private _connect(): void {
    this.socket$ = webSocket<WsMessage>({
      url: WS_URL,
      openObserver: {
        next: () => {
          this.isConnected.set(true);
          this.reconnectCount.set(0);
          console.log('[WS] Connected');
        }
      },
      closeObserver: {
        next: () => {
          this.isConnected.set(false);
          console.log('[WS] Disconnected');
        }
      },
    });

    this.messages$ = this.socket$.pipe(
      catchError(err => {
        console.warn('[WS] Error:', err);
        return EMPTY;
      }),
      retry({
        delay: (_, retryCount) => {
          this.reconnectCount.set(retryCount);
          return timer(RECONNECT_INTERVAL_MS);
        },
      }),
      share(),
      takeUntil(this.destroy$),
    );

    // Keep alive — ping every 25s
    timer(25000, 25000).pipe(takeUntil(this.destroy$)).subscribe(() => {
      this.send({ type: 'ping' });
    });
  }

  /** Listen for a specific message type */
  on<T>(type: WsMessageType): Observable<WsMessage<T>> {
    return this.messages$.pipe(
      filter(msg => msg.type === type),
      map(msg => msg as WsMessage<T>),
    );
  }

  /** Listen to all messages */
  get all$(): Observable<WsMessage> {
    return this.messages$;
  }

  /** Send a message to the backend */
  send(msg: Record<string, unknown>): void {
    if (this.isConnected()) {
      this.socket$.next(msg as unknown as WsMessage);
    }
  }

  /** Simulate an event from the browser */
  simulateEvent(eventType: string, extra: Record<string, unknown> = {}): void {
    this.send({ type: 'simulate_event', event_type: eventType, ...extra });
  }

  ngOnDestroy(): void {
    this.destroy$.next();
    this.destroy$.complete();
    this.socket$.complete();
  }
}
