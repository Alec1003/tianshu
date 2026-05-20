import Game from "@/game/Game";
import Scenario from "@/game/Scenario";
import Aircraft from "@/game/units/Aircraft";
import Ship from "@/game/units/Ship";

function createScenario() {
  return new Scenario({
    id: "scenario-1",
    name: "Route test",
    startTime: 0,
    duration: 3600,
    aircraft: [
      new Aircraft({
        id: "aircraft-1",
        name: "Aircraft 1",
        sideId: "BLUE",
        className: "Fighter",
        latitude: 10,
        longitude: 20,
        altitude: 0,
        heading: 0,
        speed: 100,
        currentFuel: 1000,
        maxFuel: 1000,
        fuelRate: 100,
        range: 100,
        sideColor: "blue",
      }),
    ],
    ships: [
      new Ship({
        id: "ship-1",
        name: "Ship 1",
        sideId: "BLUE",
        className: "Destroyer",
        latitude: 30,
        longitude: 40,
        altitude: 0,
        heading: 0,
        speed: 20,
        currentFuel: 1000,
        maxFuel: 1000,
        fuelRate: 100,
        range: 100,
        sideColor: "blue",
      }),
    ],
  });
}

describe("Game route commits", () => {
  test("commits aircraft routes without keeping desiredRoute references", () => {
    const game = new Game(createScenario());
    const aircraft = game.currentScenario.getAircraft("aircraft-1");
    expect(aircraft).toBeDefined();

    game.moveAircraft("aircraft-1", 11, 21);
    game.moveAircraft("aircraft-1", 12, 22);
    game.commitRoute("aircraft-1");

    expect(aircraft?.route).toStrictEqual([
      [11, 21],
      [12, 22],
    ]);
    expect(aircraft?.desiredRoute).toStrictEqual([]);

    const committedRoute = aircraft?.route;
    game.moveAircraft("aircraft-1", 13, 23);

    expect(aircraft?.route).toBe(committedRoute);
    expect(aircraft?.route).toStrictEqual([
      [11, 21],
      [12, 22],
    ]);
    expect(aircraft?.desiredRoute).toStrictEqual([[13, 23]]);
  });

  test("commits ship routes without keeping desiredRoute references", () => {
    const game = new Game(createScenario());
    const ship = game.currentScenario.getShip("ship-1");
    expect(ship).toBeDefined();

    game.moveShip("ship-1", 31, 41);
    game.moveShip("ship-1", 32, 42);
    game.commitRoute("ship-1");

    expect(ship?.route).toStrictEqual([
      [31, 41],
      [32, 42],
    ]);
    expect(ship?.desiredRoute).toStrictEqual([]);

    const committedRoute = ship?.route;
    game.moveShip("ship-1", 33, 43);

    expect(ship?.route).toBe(committedRoute);
    expect(ship?.route).toStrictEqual([
      [31, 41],
      [32, 42],
    ]);
    expect(ship?.desiredRoute).toStrictEqual([[33, 43]]);
  });
});
