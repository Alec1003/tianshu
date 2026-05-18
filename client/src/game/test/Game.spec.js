import { getTestGame } from "../../testing/helpers";
import Weapon from "../units/Weapon";
import { SimulationLogType } from "../log/SimulationLogs";
import { DoctrineType } from "../Doctrine";
import StrikeMission from "../mission/StrikeMission";
import {
  weaponCanEngageTarget,
  weaponEngagement,
} from "../engine/weaponEngagement";
import {
  getDistanceBetweenTwoPoints,
  getTerminalCoordinatesFromDistanceAndBearing,
} from "../../utils/mapFunctions";
import { NAUTICAL_MILES_TO_METERS } from "../../utils/constants";

function createTestWeapon(overrides = {}) {
  return new Weapon({
    id: "weapon",
    name: "Test Weapon",
    sideId: "BLUE",
    className: "Test Weapon",
    latitude: 0,
    longitude: 0,
    altitude: 0,
    heading: 0,
    speed: 1000,
    currentFuel: 100,
    maxFuel: 100,
    fuelRate: 1,
    range: 100,
    route: [],
    sideColor: "blue",
    targetId: null,
    lethality: 1,
    maxQuantity: 1,
    currentQuantity: 1,
    ...overrides,
  });
}

describe("aircraft rtb", () => {
  test("aircraft stops returning to airbase if airbase is deleted (bug #42)", () => {
    const testGame = getTestGame();
    const testScenario = testGame.currentScenario;
    const testAircraft = testScenario.getAircraft("5");
    const testAirbase = testScenario.getAirbase("3");
    expect(testAircraft.homeBaseId).toBe(testAirbase.id);
    expect(testAircraft.rtb).toBe(false);
    testGame.aircraftReturnToBase(testAircraft.id);
    expect(testAircraft.rtb).toBe(true);
    expect(testAircraft.route.length).toBe(1);
    expect(testAircraft.route[0][0]).toBe(testAirbase.latitude);
    expect(testAircraft.route[0][1]).toBe(testAirbase.longitude);
    testGame.removeAirbase(testAirbase.id);
    expect(testAircraft.rtb).toBe(false);
    expect(testAircraft.homeBaseId).toBe("");
    expect(testAircraft.route.length).toBe(0);
  });

  test("aircraft stops returning to ship if ship is deleted (bug #42)", () => {
    const testGame = getTestGame();
    const testScenario = testGame.currentScenario;
    const testAircraft = testScenario.getAircraft("5");
    const testShip = testScenario.getShip("6");
    testAircraft.homeBaseId = testShip.id;
    expect(testAircraft.homeBaseId).toBe(testShip.id);
    expect(testAircraft.rtb).toBe(false);
    testGame.aircraftReturnToBase(testAircraft.id);
    expect(testAircraft.rtb).toBe(true);
    expect(testAircraft.route.length).toBe(1);
    expect(testAircraft.route[0][0]).toBe(testShip.latitude);
    expect(testAircraft.route[0][1]).toBe(testShip.longitude);
    testGame.removeShip(testShip.id);
    expect(testAircraft.rtb).toBe(false);
    expect(testAircraft.homeBaseId).toBe("");
    expect(testAircraft.route.length).toBe(0);
  });
});

describe("scenario loading", () => {
  test("replaces legacy sample weapons with real weapon database entries", () => {
    const testGame = getTestGame();
    const scenarioString = testGame.exportCurrentScenario();

    testGame.loadScenario(scenarioString);

    const loadedAircraftWeapon =
      testGame.currentScenario.getAircraft("5").weapons[0];
    const loadedShipWeapon = testGame.currentScenario.getShip("6").weapons[0];
    const loadedFacilityWeapon =
      testGame.currentScenario.getFacility("7").weapons[0];
    const loadedInFlightWeapon = testGame.currentScenario.getWeapon("4");
    const loadedWeapons = [
      loadedAircraftWeapon,
      loadedShipWeapon,
      loadedFacilityWeapon,
      loadedInFlightWeapon,
    ];

    loadedWeapons.forEach((weapon) => {
      const template = testGame.unitDba
        .getWeaponDb()
        .find(
          (weaponTemplate) => weaponTemplate.className === weapon.className
        );

      expect(weapon.name).not.toBe("Sample Weapon");
      expect(weapon.className).not.toBe("Sample Weapon");
      expect(template).toBeTruthy();
      expect(weapon.name).toBe(weapon.className);
      expect(weapon.speed).toBe(template.speed);
      expect(weapon.maxFuel).toBe(template.maxFuel);
      expect(weapon.fuelRate).toBe(template.fuelRate);
      expect(weapon.range).toBe(template.range);
      expect(weapon.lethality).toBe(template.lethality);
    });
    expect([
      "AIM-120 AMRAAM",
      "AIM-9 Sidewinder",
      "AGM-65 Maverick",
      "AGM-158 JASSM",
    ]).toContain(loadedAircraftWeapon.className);
    expect(loadedAircraftWeapon.range).toBeGreaterThanOrEqual(90);
    expect([
      "RIM-174 Standard SM-6",
      "RIM-116 RAM",
      "RGM-84 Harpoon",
    ]).toContain(loadedShipWeapon.className);
    expect([
      "48N6 (S-400 Triumf)",
      "9M96 (S-300V4)",
      "57E6E (Pantsir-S1)",
    ]).toContain(loadedFacilityWeapon.className);
  });
});

describe("attack authorization", () => {
  test("aircraft cannot launch at a non-hostile target", () => {
    const testGame = getTestGame();
    const testScenario = testGame.currentScenario;
    const testAircraft = testScenario.getAircraft("5");
    const target = testScenario.getFacility("7");
    const initialWeaponCount = testScenario.weapons.length;

    testGame.handleAircraftAttack(testAircraft.id, target.id, "4", 1);

    expect(testScenario.weapons.length).toBe(initialWeaponCount);
    expect(testAircraft.weapons[0].currentQuantity).toBe(20);
  });

  test("aircraft cannot launch at a hostile target outside weapon range", () => {
    const testGame = getTestGame();
    const testScenario = testGame.currentScenario;
    const testAircraft = testScenario.getAircraft("5");
    const target = testScenario.getFacility("7");
    const initialWeaponCount = testScenario.weapons.length;

    target.latitude = 30;
    testAircraft.weapons[0].range = 1;
    testScenario.relationships.addHostile("BLUE", "RED");
    testGame.handleAircraftAttack(testAircraft.id, target.id, "4", 1);

    expect(testScenario.weapons.length).toBe(initialWeaponCount);
    expect(testAircraft.weapons[0].currentQuantity).toBe(20);
  });

  test("aircraft launches at a hostile target inside weapon range", () => {
    const testGame = getTestGame();
    const testScenario = testGame.currentScenario;
    const testAircraft = testScenario.getAircraft("5");
    const target = testScenario.getFacility("7");
    const initialWeaponCount = testScenario.weapons.length;

    testAircraft.weapons[0].range = 100;
    testScenario.relationships.addHostile("BLUE", "RED");
    testGame.handleAircraftAttack(testAircraft.id, target.id, "4", 1);

    expect(testScenario.weapons.length).toBe(initialWeaponCount + 1);
    expect(testAircraft.weapons[0].currentQuantity).toBe(19);
    expect(testScenario.weapons.at(-1).targetId).toBe(target.id);
  });

  test("aircraft can launch at a hostile target exactly at weapon max range", () => {
    const testGame = getTestGame();
    const testScenario = testGame.currentScenario;
    const testAircraft = testScenario.getAircraft("5");
    const target = testScenario.getFacility("7");
    const initialWeaponCount = testScenario.weapons.length;
    const rangeNm = 50;
    const targetCoordinates = getTerminalCoordinatesFromDistanceAndBearing(
      testAircraft.latitude,
      testAircraft.longitude,
      (rangeNm * NAUTICAL_MILES_TO_METERS) / 1000,
      90
    );

    target.latitude = targetCoordinates[0];
    target.longitude = targetCoordinates[1];
    testAircraft.weapons[0].range =
      (getDistanceBetweenTwoPoints(
        testAircraft.latitude,
        testAircraft.longitude,
        target.latitude,
        target.longitude
      ) *
        1000) /
      NAUTICAL_MILES_TO_METERS;
    testScenario.relationships.addHostile("BLUE", "RED");
    testGame.handleAircraftAttack(testAircraft.id, target.id, "4", 1);

    expect(testScenario.weapons.length).toBe(initialWeaponCount + 1);
    expect(testAircraft.weapons[0].currentQuantity).toBe(19);
    expect(testScenario.weapons.at(-1).targetId).toBe(target.id);
  });

  test("aircraft launches at a hostile airbase inside weapon range", () => {
    const testGame = getTestGame();
    const testScenario = testGame.currentScenario;
    const testAircraft = testScenario.getAircraft("5");
    const target = testScenario.getAirbase("3");
    const initialWeaponCount = testScenario.weapons.length;

    target.sideId = "RED";
    target.latitude = testAircraft.latitude;
    target.longitude = testAircraft.longitude;
    testAircraft.weapons[0].range = 100;
    testScenario.relationships.addHostile("BLUE", "RED");
    testGame.handleAircraftAttack(testAircraft.id, target.id, "4", 1);

    expect(testScenario.weapons.length).toBe(initialWeaponCount + 1);
    expect(testAircraft.weapons[0].currentQuantity).toBe(19);
    expect(testScenario.weapons.at(-1).targetId).toBe(target.id);
  });

  test("aircraft clears a stale air-to-air target", () => {
    const testGame = getTestGame();
    const testAircraft = testGame.currentScenario.getAircraft("5");

    testAircraft.targetId = "missing-target";
    testGame.aircraftAirToAirEngagement();

    expect(testAircraft.targetId).toBe("");
  });

  test("aircraft automatically attacks hostile SAMs inside sensor and weapon range", () => {
    const testGame = getTestGame();
    const testScenario = testGame.currentScenario;
    const testAircraft = testScenario.getAircraft("5");
    const target = testScenario.getFacility("7");
    const initialWeaponCount = testScenario.weapons.length;

    target.weapons = [];
    target.latitude = testAircraft.latitude;
    target.longitude = testAircraft.longitude;
    testAircraft.range = 100;
    testAircraft.weapons[0].range = 100;
    testScenario.updateSideDoctrine("BLUE", {
      [DoctrineType.AIRCRAFT_ATTACK_HOSTILE]: true,
    });
    testScenario.relationships.addHostile("BLUE", "RED");

    testGame.aircraftSurfaceEngagement();

    expect(testScenario.weapons.length).toBe(initialWeaponCount + 1);
    expect(testAircraft.weapons[0].currentQuantity).toBe(19);
    expect(testScenario.weapons.at(-1).targetId).toBe(target.id);
  });

  test("aircraft does not repeatedly launch while a hostile SAM is already tracked", () => {
    const testGame = getTestGame();
    const testScenario = testGame.currentScenario;
    const testAircraft = testScenario.getAircraft("5");
    const target = testScenario.getFacility("7");

    target.weapons = [];
    target.latitude = testAircraft.latitude;
    target.longitude = testAircraft.longitude;
    testAircraft.range = 100;
    testAircraft.weapons[0].range = 100;
    testScenario.updateSideDoctrine("BLUE", {
      [DoctrineType.AIRCRAFT_ATTACK_HOSTILE]: true,
    });
    testScenario.relationships.addHostile("BLUE", "RED");

    testGame.aircraftSurfaceEngagement();
    const weaponCountAfterFirstLaunch = testScenario.weapons.length;
    expect(weaponCountAfterFirstLaunch).toBeGreaterThan(1);
    testGame.aircraftSurfaceEngagement();

    expect(testScenario.weapons.length).toBe(weaponCountAfterFirstLaunch);
  });
});

describe("weapon engagement", () => {
  test("an intercepted weapon cannot still hit its target in the same tick", () => {
    const testGame = getTestGame();
    const testScenario = testGame.currentScenario;
    const targetShip = testScenario.getShip("6");
    targetShip.latitude = 0;
    targetShip.longitude = 0;
    targetShip.weapons = [];
    testScenario.aircraft = [];
    testScenario.facilities = [];

    const incomingWeapon = createTestWeapon({
      id: "incoming-weapon",
      name: "Incoming Weapon",
      sideId: "RED",
      sideColor: "red",
      targetId: targetShip.id,
      route: [[targetShip.latitude, targetShip.longitude]],
    });
    const interceptor = createTestWeapon({
      id: "interceptor",
      name: "Interceptor",
      targetId: incomingWeapon.id,
      route: [[incomingWeapon.latitude, incomingWeapon.longitude]],
    });
    testScenario.weapons = [interceptor, incomingWeapon];

    testGame.updateGameState();

    expect(testScenario.getWeapon(incomingWeapon.id)).toBeUndefined();
    expect(testScenario.getShip(targetShip.id)).toBe(targetShip);
  });

  test("a weapon that reaches the target this tick hits before fuel depletion is applied", () => {
    const testGame = getTestGame();
    const testScenario = testGame.currentScenario;
    const target = testScenario.getFacility("7");
    target.latitude = 0.02;
    target.longitude = 0;
    const weapon = createTestWeapon({
      id: "arriving-weapon",
      targetId: target.id,
      speed: 100000,
      currentFuel: 1,
      fuelRate: 3600,
      route: [[target.latitude, target.longitude]],
    });
    testScenario.weapons = [weapon];

    weaponEngagement(testScenario, weapon, testGame.simulationLogs);

    expect(testScenario.getFacility(target.id)).toBeUndefined();
    expect(
      testGame.simulationLogs.getLogs(undefined, [
        SimulationLogType.WEAPON_CRASHED,
      ])
    ).toHaveLength(0);
  });

  test("weapon range checks include the exact maximum range", () => {
    const testGame = getTestGame();
    const target = testGame.currentScenario.getFacility("7");
    const weapon = createTestWeapon();
    const targetCoordinates = getTerminalCoordinatesFromDistanceAndBearing(
      weapon.latitude,
      weapon.longitude,
      (weapon.range * NAUTICAL_MILES_TO_METERS) / 1000,
      90
    );
    target.latitude = targetCoordinates[0];
    target.longitude = targetCoordinates[1];
    weapon.range =
      (getDistanceBetweenTwoPoints(
        weapon.latitude,
        weapon.longitude,
        target.latitude,
        target.longitude
      ) *
        1000) /
      NAUTICAL_MILES_TO_METERS;

    expect(weaponCanEngageTarget(target, weapon)).toBe(true);
  });
});

describe("mission assignment conflicts", () => {
  test("createStrikeMission filters out attackers already used by another mission", () => {
    const testGame = getTestGame();
    const testScenario = testGame.currentScenario;
    const testAircraft = testScenario.getAircraft("5");
    const target = testScenario.getFacility("7");

    testGame.createStrikeMission(
      "mission-A",
      [testAircraft.id],
      [target.id]
    );
    expect(testScenario.missions.length).toBe(1);

    testGame.createStrikeMission(
      "mission-B",
      [testAircraft.id],
      [target.id]
    );
    expect(testScenario.missions.length).toBe(1);
    expect(testScenario.missions[0].name).toBe("mission-A");
  });

  test("updateUnitsOnStrikeMission only appends one waypoint per attacker per tick even when duplicated across missions", () => {
    const testGame = getTestGame();
    const testScenario = testGame.currentScenario;
    const testAircraft = testScenario.getAircraft("5");
    const target = testScenario.getFacility("7");
    target.weapons = [];
    target.latitude = testAircraft.latitude + 50;
    target.longitude = testAircraft.longitude + 50;
    testAircraft.range = 5;
    testAircraft.weapons[0].range = 5;
    testScenario.relationships.addHostile("BLUE", "RED");

    testScenario.missions.push(
      new StrikeMission({
        id: "rogue-A",
        name: "rogue-A",
        sideId: "BLUE",
        assignedUnitIds: [testAircraft.id],
        assignedTargetIds: [target.id],
        active: true,
      })
    );
    testScenario.missions.push(
      new StrikeMission({
        id: "rogue-B",
        name: "rogue-B",
        sideId: "BLUE",
        assignedUnitIds: [testAircraft.id],
        assignedTargetIds: [target.id],
        active: true,
      })
    );

    const initialRouteLength = testAircraft.route.length;
    testGame.updateUnitsOnStrikeMission();
    const delta = testAircraft.route.length - initialRouteLength;

    expect(delta).toBeLessThanOrEqual(1);
  });
});
