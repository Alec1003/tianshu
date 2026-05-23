import { describe, expect, test, vi } from "vitest";

import type { RuntimeSnapshot } from "@/api/types";
import RuntimeController, { type RuntimeApiClient } from "./RuntimeController";

function makeSnapshot(
  action: string,
  overrides: Partial<RuntimeSnapshot> = {}
): RuntimeSnapshot {
  return {
    ok: true,
    action,
    state: {},
    running: false,
    paused: true,
    current_time: 100,
    elapsed: 0,
    duration_left: 600,
    outcome: {
      ended: false,
      winner_side_id: null,
      reason: "",
      ended_at: 0,
      objective_destroyed: null,
      time_up: false,
    },
    scenario: { currentScenario: { id: action } },
    ...overrides,
  };
}

function makeApi(): RuntimeApiClient {
  return {
    getSnapshot: vi.fn(async () => makeSnapshot("snapshot")),
    loadScenario: vi.fn(async () => makeSnapshot("load")),
    start: vi.fn(async () => makeSnapshot("start", { running: true, paused: false })),
    pause: vi.fn(async () => makeSnapshot("pause")),
    reset: vi.fn(async () => makeSnapshot("reset")),
    step: vi.fn(async (steps = 1) =>
      makeSnapshot("step", {
        current_time: 100 + steps,
        elapsed: steps,
        duration_left: 600 - steps,
        state: { steps },
      })
    ),
    attack: vi.fn(async (attack) =>
      makeSnapshot("attack", {
        state: { attacked: true, ...attack },
      })
    ),
  };
}

describe("RuntimeController", () => {
  test("stores the latest backend snapshot", async () => {
    const api = makeApi();
    const controller = new RuntimeController(api);

    const snapshot = await controller.refresh();

    expect(snapshot.action).toBe("snapshot");
    expect(controller.snapshot).toBe(snapshot);
    expect(controller.scenario).toEqual({ currentScenario: { id: "snapshot" } });
    expect(controller.outcome?.ended).toBe(false);
  });

  test("delegates control actions to the backend runtime API", async () => {
    const api = makeApi();
    const controller = new RuntimeController(api);

    await controller.start();
    expect(controller.running).toBe(true);

    await controller.step(5);
    expect(api.step).toHaveBeenCalledWith(5);
    expect(controller.currentTime).toBe(105);
    expect(controller.snapshot?.state).toEqual({ steps: 5 });

    await controller.loadScenario({ currentScenario: { id: "loaded" } });
    expect(api.loadScenario).toHaveBeenCalledWith({
      currentScenario: { id: "loaded" },
    });

    await controller.attack({
      attacker_type: "aircraft",
      attacker_id: "aircraft-1",
      target_id: "target-1",
      weapon_id: "weapon-1",
      weapon_quantity: 1,
    });
    expect(api.attack).toHaveBeenCalledWith({
      attacker_type: "aircraft",
      attacker_id: "aircraft-1",
      target_id: "target-1",
      weapon_id: "weapon-1",
      weapon_quantity: 1,
    });
    expect(controller.snapshot?.action).toBe("attack");
  });
});
