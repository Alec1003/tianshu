import {
  getRuntimeSnapshot,
  loadRuntimeScenario,
  pauseRuntime,
  resetRuntime,
  startRuntime,
  stepRuntime,
  attackRuntime,
  deployRuntimeUnit,
  deleteRuntimeUnit,
  moveRuntimeUnit,
  setRuntimeUnitPosition,
  updateRuntimeUnit,
  setRuntimeCurrentSide,
  createRuntimeSide,
  updateRuntimeSide,
  deleteRuntimeSide,
  deleteRuntimeMission,
  createRuntimePatrolMission,
  updateRuntimePatrolMission,
  createRuntimeStrikeMission,
  updateRuntimeStrikeMission,
  addRuntimeWeapon,
  deleteRuntimeWeapon,
  updateRuntimeWeaponQuantity,
} from "@/api/ai";
import { setRuntimeScenarioContext } from "@/api/client";
import type {
  RuntimeAttackRequest,
  RuntimeAddWeaponRequest,
  RuntimeCreateSideRequest,
  RuntimeDeleteWeaponRequest,
  RuntimeDeployUnitRequest,
  RuntimeMoveUnitRequest,
  RuntimeOutcome,
  RuntimePatrolMissionRequest,
  RuntimeSetUnitPositionRequest,
  RuntimeSnapshot,
  RuntimeStrikeMissionRequest,
  RuntimeUnitType,
  RuntimeUpdateSideRequest,
  RuntimeUpdateUnitRequest,
  RuntimeUpdateWeaponQuantityRequest,
} from "@/api/types";

export interface RuntimeApiClient {
  getSnapshot(): Promise<RuntimeSnapshot>;
  loadScenario(scenario: Record<string, unknown>): Promise<RuntimeSnapshot>;
  start(): Promise<RuntimeSnapshot>;
  pause(): Promise<RuntimeSnapshot>;
  reset(): Promise<RuntimeSnapshot>;
  step(steps?: number): Promise<RuntimeSnapshot>;
  attack(attack: RuntimeAttackRequest): Promise<RuntimeSnapshot>;
  deployUnit(unit: RuntimeDeployUnitRequest): Promise<RuntimeSnapshot>;
  deleteUnit(
    unitType: RuntimeUnitType,
    unitId: string
  ): Promise<RuntimeSnapshot>;
  moveUnit(move: RuntimeMoveUnitRequest): Promise<RuntimeSnapshot>;
  setUnitPosition(
    position: RuntimeSetUnitPositionRequest
  ): Promise<RuntimeSnapshot>;
  updateUnit(update: RuntimeUpdateUnitRequest): Promise<RuntimeSnapshot>;
  setCurrentSide(side: string): Promise<RuntimeSnapshot>;
  createSide(side: RuntimeCreateSideRequest): Promise<RuntimeSnapshot>;
  updateSide(
    sideId: string,
    side: RuntimeUpdateSideRequest
  ): Promise<RuntimeSnapshot>;
  deleteSide(sideId: string): Promise<RuntimeSnapshot>;
  deleteMission(missionId: string): Promise<RuntimeSnapshot>;
  createPatrolMission(
    mission: RuntimePatrolMissionRequest
  ): Promise<RuntimeSnapshot>;
  updatePatrolMission(
    missionId: string,
    mission: RuntimePatrolMissionRequest
  ): Promise<RuntimeSnapshot>;
  createStrikeMission(
    mission: RuntimeStrikeMissionRequest
  ): Promise<RuntimeSnapshot>;
  updateStrikeMission(
    missionId: string,
    mission: RuntimeStrikeMissionRequest
  ): Promise<RuntimeSnapshot>;
  addWeapon(weapon: RuntimeAddWeaponRequest): Promise<RuntimeSnapshot>;
  deleteWeapon(weapon: RuntimeDeleteWeaponRequest): Promise<RuntimeSnapshot>;
  updateWeaponQuantity(
    weapon: RuntimeUpdateWeaponQuantityRequest
  ): Promise<RuntimeSnapshot>;
}

const defaultRuntimeApiClient: RuntimeApiClient = {
  getSnapshot: getRuntimeSnapshot,
  loadScenario: loadRuntimeScenario,
  start: startRuntime,
  pause: pauseRuntime,
  reset: resetRuntime,
  step: stepRuntime,
  attack: attackRuntime,
  deployUnit: deployRuntimeUnit,
  deleteUnit: deleteRuntimeUnit,
  moveUnit: moveRuntimeUnit,
  setUnitPosition: setRuntimeUnitPosition,
  updateUnit: updateRuntimeUnit,
  setCurrentSide: setRuntimeCurrentSide,
  createSide: createRuntimeSide,
  updateSide: updateRuntimeSide,
  deleteSide: deleteRuntimeSide,
  deleteMission: deleteRuntimeMission,
  createPatrolMission: createRuntimePatrolMission,
  updatePatrolMission: updateRuntimePatrolMission,
  createStrikeMission: createRuntimeStrikeMission,
  updateStrikeMission: updateRuntimeStrikeMission,
  addWeapon: addRuntimeWeapon,
  deleteWeapon: deleteRuntimeWeapon,
  updateWeaponQuantity: updateRuntimeWeaponQuantity,
};

export default class RuntimeController {
  private latestSnapshot: RuntimeSnapshot | null = null;

  constructor(
    private readonly api: RuntimeApiClient = defaultRuntimeApiClient,
    runtimeScenarioId: string | null | undefined = ""
  ) {
    setRuntimeScenarioContext(runtimeScenarioId);
  }

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

  async attack(attack: RuntimeAttackRequest): Promise<RuntimeSnapshot> {
    return this.setSnapshot(await this.api.attack(attack));
  }

  async deployUnit(unit: RuntimeDeployUnitRequest): Promise<RuntimeSnapshot> {
    return this.setSnapshot(await this.api.deployUnit(unit));
  }

  async deleteUnit(
    unitType: RuntimeUnitType,
    unitId: string
  ): Promise<RuntimeSnapshot> {
    return this.setSnapshot(await this.api.deleteUnit(unitType, unitId));
  }

  async moveUnit(move: RuntimeMoveUnitRequest): Promise<RuntimeSnapshot> {
    return this.setSnapshot(await this.api.moveUnit(move));
  }

  async setUnitPosition(
    position: RuntimeSetUnitPositionRequest
  ): Promise<RuntimeSnapshot> {
    return this.setSnapshot(await this.api.setUnitPosition(position));
  }

  async updateUnit(update: RuntimeUpdateUnitRequest): Promise<RuntimeSnapshot> {
    return this.setSnapshot(await this.api.updateUnit(update));
  }

  async setCurrentSide(side: string): Promise<RuntimeSnapshot> {
    return this.setSnapshot(await this.api.setCurrentSide(side));
  }

  async createSide(side: RuntimeCreateSideRequest): Promise<RuntimeSnapshot> {
    return this.setSnapshot(await this.api.createSide(side));
  }

  async updateSide(
    sideId: string,
    side: RuntimeUpdateSideRequest
  ): Promise<RuntimeSnapshot> {
    return this.setSnapshot(await this.api.updateSide(sideId, side));
  }

  async deleteSide(sideId: string): Promise<RuntimeSnapshot> {
    return this.setSnapshot(await this.api.deleteSide(sideId));
  }

  async deleteMission(missionId: string): Promise<RuntimeSnapshot> {
    return this.setSnapshot(await this.api.deleteMission(missionId));
  }

  async createPatrolMission(
    mission: RuntimePatrolMissionRequest
  ): Promise<RuntimeSnapshot> {
    return this.setSnapshot(await this.api.createPatrolMission(mission));
  }

  async updatePatrolMission(
    missionId: string,
    mission: RuntimePatrolMissionRequest
  ): Promise<RuntimeSnapshot> {
    return this.setSnapshot(
      await this.api.updatePatrolMission(missionId, mission)
    );
  }

  async createStrikeMission(
    mission: RuntimeStrikeMissionRequest
  ): Promise<RuntimeSnapshot> {
    return this.setSnapshot(await this.api.createStrikeMission(mission));
  }

  async updateStrikeMission(
    missionId: string,
    mission: RuntimeStrikeMissionRequest
  ): Promise<RuntimeSnapshot> {
    return this.setSnapshot(
      await this.api.updateStrikeMission(missionId, mission)
    );
  }

  async addWeapon(weapon: RuntimeAddWeaponRequest): Promise<RuntimeSnapshot> {
    return this.setSnapshot(await this.api.addWeapon(weapon));
  }

  async deleteWeapon(
    weapon: RuntimeDeleteWeaponRequest
  ): Promise<RuntimeSnapshot> {
    return this.setSnapshot(await this.api.deleteWeapon(weapon));
  }

  async updateWeaponQuantity(
    weapon: RuntimeUpdateWeaponQuantityRequest
  ): Promise<RuntimeSnapshot> {
    return this.setSnapshot(await this.api.updateWeaponQuantity(weapon));
  }

  private setSnapshot(snapshot: RuntimeSnapshot): RuntimeSnapshot {
    this.latestSnapshot = snapshot;
    return snapshot;
  }
}

export type {
  RuntimeAttackRequest,
  RuntimeAddWeaponRequest,
  RuntimeCreateSideRequest,
  RuntimeDeleteWeaponRequest,
  RuntimeDeployUnitRequest,
  RuntimeMoveUnitRequest,
  RuntimePatrolMissionRequest,
  RuntimeSetUnitPositionRequest,
  RuntimeStrikeMissionRequest,
  RuntimeUnitType,
  RuntimeUpdateSideRequest,
  RuntimeUpdateUnitRequest,
  RuntimeUpdateWeaponQuantityRequest,
};
