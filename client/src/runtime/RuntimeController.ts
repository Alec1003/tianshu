import {
  getRuntimeSnapshot,
  loadRuntimeScenario,
  pauseRuntime,
  resetRuntime,
  startRuntime,
  stepRuntime,
} from "@/api/ai";
import type { RuntimeOutcome, RuntimeSnapshot } from "@/api/types";

export interface RuntimeApiClient {
  getSnapshot(): Promise<RuntimeSnapshot>;
  loadScenario(scenario: Record<string, unknown>): Promise<RuntimeSnapshot>;
  start(): Promise<RuntimeSnapshot>;
  pause(): Promise<RuntimeSnapshot>;
  reset(): Promise<RuntimeSnapshot>;
  step(steps?: number): Promise<RuntimeSnapshot>;
}

const defaultRuntimeApiClient: RuntimeApiClient = {
  getSnapshot: getRuntimeSnapshot,
  loadScenario: loadRuntimeScenario,
  start: startRuntime,
  pause: pauseRuntime,
  reset: resetRuntime,
  step: stepRuntime,
};

export default class RuntimeController {
  private latestSnapshot: RuntimeSnapshot | null = null;

  constructor(private readonly api: RuntimeApiClient = defaultRuntimeApiClient) {}

  get snapshot(): RuntimeSnapshot | null {
    return this.latestSnapshot;
  }

  get scenario(): Record<string, unknown> | null {
    return this.latestSnapshot?.scenario ?? null;
  }

  get outcome(): RuntimeOutcome | null {
    return this.latestSnapshot?.outcome ?? null;
  }

  get running(): boolean {
    return this.latestSnapshot?.running ?? false;
  }

  get currentTime(): number {
    return this.latestSnapshot?.current_time ?? 0;
  }

  async refresh(): Promise<RuntimeSnapshot> {
    return this.setSnapshot(await this.api.getSnapshot());
  }

  async loadScenario(
    scenario: Record<string, unknown>
  ): Promise<RuntimeSnapshot> {
    return this.setSnapshot(await this.api.loadScenario(scenario));
  }

  async start(): Promise<RuntimeSnapshot> {
    return this.setSnapshot(await this.api.start());
  }

  async pause(): Promise<RuntimeSnapshot> {
    return this.setSnapshot(await this.api.pause());
  }

  async reset(): Promise<RuntimeSnapshot> {
    return this.setSnapshot(await this.api.reset());
  }

  async step(steps: number = 1): Promise<RuntimeSnapshot> {
    return this.setSnapshot(await this.api.step(steps));
  }

  private setSnapshot(snapshot: RuntimeSnapshot): RuntimeSnapshot {
    this.latestSnapshot = snapshot;
    return snapshot;
  }
}
