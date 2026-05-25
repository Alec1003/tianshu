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
    visibility: { current_side_id: "", by_side: {} },
    ...overrides,
  };
}

function makeApi(): RuntimeApiClient {
  return {
    getSnapshot: vi.fn(async () => makeSnapshot("snapshot")),
    loadScenario: vi.fn(async () => makeSnapshot("load")),
    start: vi.fn(async () =>
      makeSnapshot("start", { running: true, paused: false })
    ),
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
    deployUnit: vi.fn(async (unit) =>
      makeSnapshot("deploy_unit", { state: { unit } })
    ),
    deleteUnit: vi.fn(async (unitType, unitId) =>
      makeSnapshot("delete_unit", { state: { unitType, unitId } })
    ),
    moveUnit: vi.fn(async (move) =>
      makeSnapshot("move_unit", { state: { move } })
    ),
    setUnitPosition: vi.fn(async (position) =>
      makeSnapshot("set_unit_position", { state: { position } })
    ),
    updateUnit: vi.fn(async (update) =>
      makeSnapshot("update_unit", { state: { update } })
    ),
    setCurrentSide: vi.fn(async (side) =>
      makeSnapshot("set_current_side", { state: { side } })
    ),
    createSide: vi.fn(async (side) =>
      makeSnapshot("create_side", { state: { side } })
    ),
    updateSide: vi.fn(async (sideId, side) =>
      makeSnapshot("update_side", { state: { sideId, side } })
    ),
    deleteSide: vi.fn(async (sideId) =>
      makeSnapshot("delete_side", { state: { sideId } })
    ),
    deleteMission: vi.fn(async (missionId) =>
      makeSnapshot("delete_mission", { state: { missionId } })
    ),
    createPatrolMission: vi.fn(async (mission) =>
      makeSnapshot("create_patrol_mission", { state: { mission } })
    ),
    updatePatrolMission: vi.fn(async (missionId, mission) =>
      makeSnapshot("update_patrol_mission", { state: { missionId, mission } })
    ),
    createStrikeMission: vi.fn(async (mission) =>
      makeSnapshot("create_strike_mission", { state: { mission } })
    ),
    updateStrikeMission: vi.fn(async (missionId, mission) =>
      makeSnapshot("update_strike_mission", { state: { missionId, mission } })
    ),
    addWeapon: vi.fn(async (weapon) =>
      makeSnapshot("add_weapon", { state: { weapon } })
    ),
    deleteWeapon: vi.fn(async (weapon) =>
      makeSnapshot("delete_weapon", { state: { weapon } })
    ),
    updateWeaponQuantity: vi.fn(async (weapon) =>
      makeSnapshot("update_weapon_quantity", { state: { weapon } })
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
    expect(controller.scenario).toEqual({
      currentScenario: { id: "snapshot" },
    });
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

    await controller.deployUnit({
      unit_type: "aircraft",
      class_name: "F-35A Lightning II",
      latitude: 1,
      longitude: 2,
    });
    expect(api.deployUnit).toHaveBeenCalledWith({
      unit_type: "aircraft",
      class_name: "F-35A Lightning II",
      latitude: 1,
      longitude: 2,
    });

    await controller.setCurrentSide("blue");
    expect(api.setCurrentSide).toHaveBeenCalledWith("blue");

    await controller.addWeapon({
      unit_type: "aircraft",
      unit_id: "aircraft-1",
      class_name: "AIM-120 AMRAAM",
      speed: 2600,
      max_fuel: 480,
      fuel_rate: 350,
      range: 86,
      lethality: 0.65,
      quantity: 2,
    });
    expect(api.addWeapon).toHaveBeenCalledWith({
      unit_type: "aircraft",
      unit_id: "aircraft-1",
      class_name: "AIM-120 AMRAAM",
      speed: 2600,
      max_fuel: 480,
      fuel_rate: 350,
      range: 86,
      lethality: 0.65,
      quantity: 2,
    });

    await controller.updateWeaponQuantity({
      unit_type: "aircraft",
      unit_id: "aircraft-1",
      weapon_id: "weapon-1",
      increment: -1,
    });
    expect(api.updateWeaponQuantity).toHaveBeenCalledWith({
      unit_type: "aircraft",
      unit_id: "aircraft-1",
      weapon_id: "weapon-1",
      increment: -1,
    });

    await controller.deleteWeapon({
      unit_type: "aircraft",
      unit_id: "aircraft-1",
      weapon_id: "weapon-1",
    });
    expect(api.deleteWeapon).toHaveBeenCalledWith({
      unit_type: "aircraft",
      unit_id: "aircraft-1",
      weapon_id: "weapon-1",
    });
  });
});
