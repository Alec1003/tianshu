import Game from "@/game/Game";
import Scenario from "@/game/Scenario";
import Side from "@/game/Side";
import Aircraft from "@/game/units/Aircraft";
import Ship from "@/game/units/Ship";
import {
  OBJECTIVE_BONUS_SCORE,
  UNIT_SCORE_TABLE,
  onUnitDestroyed,
} from "@/game/engine/weaponEngagement";

function makeAircraft(
  partial: Partial<ConstructorParameters<typeof Aircraft>[0]> & {
    id: string;
    sideId: string;
  }
): Aircraft {
  return new Aircraft({
    id: partial.id,
    name: partial.name ?? partial.id,
    sideId: partial.sideId,
    className: partial.className ?? "F-16C",
    latitude: partial.latitude ?? 0,
    longitude: partial.longitude ?? 0,
    altitude: 10000,
    heading: 90,
    speed: partial.speed ?? 500,
    currentFuel: 10000,
    maxFuel: 10000,
    fuelRate: 5000,
    range: 100,
    sideColor: partial.sideColor ?? "blue",
    isObjective: partial.isObjective ?? false,
  });
}

function makeShip(
  partial: Partial<ConstructorParameters<typeof Ship>[0]> & {
    id: string;
    sideId: string;
  }
): Ship {
  return new Ship({
    id: partial.id,
    name: partial.name ?? partial.id,
    sideId: partial.sideId,
    className: partial.className ?? "Destroyer",
    latitude: partial.latitude ?? 0,
    longitude: partial.longitude ?? 0,
    altitude: 0,
    heading: 0,
    speed: 30,
    currentFuel: 1000000,
    maxFuel: 1000000,
    fuelRate: 100000,
    range: 200,
    sideColor: partial.sideColor ?? "red",
    isObjective: partial.isObjective ?? false,
  });
}

function makeTwoSideScenario(opts?: { duration?: number }): {
  blue: Side;
  red: Side;
  scenario: Scenario;
  game: Game;
} {
  const blue = new Side({ id: "blue-1", name: "BLUE", color: "blue" });
  const red = new Side({ id: "red-1", name: "RED", color: "red" });
  const scenario = new Scenario({
    id: "sc-1",
    name: "Victory Test",
    startTime: 1000,
    currentTime: 1000,
    duration: opts?.duration ?? 14400,
    sides: [blue, red],
  });
  const game = new Game(scenario);
  return { blue, red, scenario, game };
}

describe("Scoring (onUnitDestroyed)", () => {
  test("regular aircraft kill grants UNIT_SCORE_TABLE.aircraft to attacker", () => {
    const { blue, red, scenario } = makeTwoSideScenario();
    const target = makeAircraft({ id: "ac1", sideId: red.id });
    scenario.aircraft.push(target);

    onUnitDestroyed(scenario, blue.id, target);

    expect(blue.totalScore).toBe(UNIT_SCORE_TABLE.aircraft);
    expect(red.totalScore).toBe(0);
    expect(scenario.lastObjectiveDestroyed).toBeNull();
  });

  test("ship kill grants UNIT_SCORE_TABLE.ship and is more valuable than aircraft", () => {
    const { blue, red, scenario } = makeTwoSideScenario();
    const target = makeShip({ id: "sh1", sideId: red.id });
    scenario.ships.push(target);

    onUnitDestroyed(scenario, blue.id, target);

    expect(blue.totalScore).toBe(UNIT_SCORE_TABLE.ship);
    expect(UNIT_SCORE_TABLE.ship).toBeGreaterThan(UNIT_SCORE_TABLE.aircraft);
  });

  test("objective kill grants base score + OBJECTIVE_BONUS_SCORE and records event", () => {
    const { blue, red, scenario } = makeTwoSideScenario();
    const target = makeAircraft({
      id: "vip1",
      sideId: red.id,
      isObjective: true,
    });
    scenario.aircraft.push(target);

    onUnitDestroyed(scenario, blue.id, target);

    expect(blue.totalScore).toBe(
      UNIT_SCORE_TABLE.aircraft + OBJECTIVE_BONUS_SCORE
    );
    expect(scenario.lastObjectiveDestroyed).not.toBeNull();
    expect(scenario.lastObjectiveDestroyed?.attackerSideId).toBe(blue.id);
    expect(scenario.lastObjectiveDestroyed?.victimSideId).toBe(red.id);
    expect(scenario.lastObjectiveDestroyed?.unitType).toBe("aircraft");
    expect(scenario.lastObjectiveDestroyed?.unitId).toBe("vip1");
  });

  test("unknown attackerSideId is silently ignored (no crash, no score)", () => {
    const { blue, red, scenario } = makeTwoSideScenario();
    const target = makeAircraft({ id: "ac1", sideId: red.id });

    expect(() =>
      onUnitDestroyed(scenario, "non-existent-side", target)
    ).not.toThrow();
    expect(blue.totalScore).toBe(0);
    expect(red.totalScore).toBe(0);
  });
});

describe("Game.checkGameEnded", () => {
  test("returns false on fresh scenario with units on both sides", () => {
    const { blue, red, scenario, game } = makeTwoSideScenario();
    scenario.aircraft.push(makeAircraft({ id: "a1", sideId: blue.id }));
    scenario.aircraft.push(makeAircraft({ id: "a2", sideId: red.id }));

    expect(game.checkGameEnded()).toBe(false);
    expect(game.gameOutcome.ended).toBe(false);
  });

  test("KEY_UNIT_DESTROYED: scenario.lastObjectiveDestroyed triggers ended + winner", () => {
    const { blue, red, scenario, game } = makeTwoSideScenario();
    scenario.aircraft.push(makeAircraft({ id: "a1", sideId: blue.id }));
    scenario.aircraft.push(makeAircraft({ id: "a2", sideId: red.id }));

    const vip = makeAircraft({
      id: "vip-red",
      sideId: red.id,
      isObjective: true,
    });
    scenario.aircraft.push(vip);
    // 模拟 weaponEndgame 命中：先调 onUnitDestroyed，再 tick
    onUnitDestroyed(scenario, blue.id, vip);

    expect(game.checkGameEnded()).toBe(true);
    expect(game.gameOutcome.ended).toBe(true);
    expect(game.gameOutcome.reason).toBe("KEY_UNIT_DESTROYED");
    expect(game.gameOutcome.winnerSideId).toBe(blue.id);
  });

  test("side with zero combat units does NOT end the game (waits for KEY_UNIT or TIMEOUT)", () => {
    const { blue, red: _red, scenario, game } = makeTwoSideScenario();
    // 只剩蓝方有单位，红方全灭——但新规则下全灭不再是胜利条件
    scenario.aircraft.push(makeAircraft({ id: "a1", sideId: blue.id }));

    expect(game.checkGameEnded()).toBe(false);
    expect(game.gameOutcome.ended).toBe(false);
  });

  test("TIMEOUT: at duration limit, highest-score side wins", () => {
    const { blue, red, scenario, game } = makeTwoSideScenario({
      duration: 60,
    });
    scenario.aircraft.push(makeAircraft({ id: "a1", sideId: blue.id }));
    scenario.aircraft.push(makeAircraft({ id: "a2", sideId: red.id }));
    blue.totalScore = 50;
    red.totalScore = 30;

    // 把 currentTime 推到超时点
    scenario.currentTime = scenario.startTime + 60;

    expect(game.checkGameEnded()).toBe(true);
    expect(game.gameOutcome.reason).toBe("TIMEOUT");
    expect(game.gameOutcome.winnerSideId).toBe(blue.id);
  });

  test("priority: KEY_UNIT_DESTROYED beats TIMEOUT when both conditions match", () => {
    const { blue, red, scenario, game } = makeTwoSideScenario({ duration: 60 });
    scenario.aircraft.push(makeAircraft({ id: "a1", sideId: blue.id }));
    const vip = makeAircraft({
      id: "vip-red",
      sideId: red.id,
      isObjective: true,
    });
    scenario.aircraft.push(vip);
    // 击毁关键单位同时推到超时点
    onUnitDestroyed(scenario, blue.id, vip);
    scenario.currentTime = scenario.startTime + 60;
    // TIMEOUT 下红方总分更高，以验证 KEY_UNIT_DESTROYED 优先于 TIMEOUT 的打分裁定
    blue.totalScore = 0;
    red.totalScore = 9999;

    expect(game.checkGameEnded()).toBe(true);
    expect(game.gameOutcome.reason).toBe("KEY_UNIT_DESTROYED");
    // 胜方 = 击毁关键单位的攻方（蓝方），而不是 TIMEOUT 按分裁定的红方
    expect(game.gameOutcome.winnerSideId).toBe(blue.id);
  });

  test("TIMEOUT decides winner by score when no KEY_UNIT_DESTROYED occurred", () => {
    const { blue, red, scenario, game } = makeTwoSideScenario({ duration: 60 });
    scenario.aircraft.push(makeAircraft({ id: "a1", sideId: blue.id }));
    // 红方全灭，关键单位未被击毁。超时后按总分裁定。
    blue.totalScore = 100;
    red.totalScore = 50;
    scenario.currentTime = scenario.startTime + 60;

    expect(game.checkGameEnded()).toBe(true);
    expect(game.gameOutcome.reason).toBe("TIMEOUT");
    expect(game.gameOutcome.winnerSideId).toBe(blue.id);
  });
});

describe("Game.reset", () => {
  test("soft reset clears gameOutcome / lastObjectiveDestroyed / totalScore", () => {
    const { blue, red, scenario, game } = makeTwoSideScenario();
    scenario.aircraft.push(makeAircraft({ id: "a1", sideId: blue.id }));
    blue.totalScore = 100;
    red.totalScore = 50;
    const vip = makeAircraft({ id: "vip", sideId: red.id, isObjective: true });
    onUnitDestroyed(scenario, blue.id, vip);
    game.checkGameEnded(); // 设置 ended=true

    expect(game.gameOutcome.ended).toBe(true);

    game.reset();

    expect(game.gameOutcome.ended).toBe(false);
    expect(game.gameOutcome.reason).toBe("");
    expect(scenario.lastObjectiveDestroyed).toBeNull();
    expect(blue.totalScore).toBe(0);
    expect(red.totalScore).toBe(0);
  });
});
