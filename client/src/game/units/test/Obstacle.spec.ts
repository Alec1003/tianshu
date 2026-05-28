import Game from "@/game/Game";
import Scenario from "@/game/Scenario";
import Obstacle from "@/game/units/Obstacle";

describe("Obstacle", () => {
  test("an Obstacle is instantiated with safe defaults", () => {
    const obstacle = new Obstacle({
      id: "obstacle-1",
      name: "禁行区",
      className: "禁行区",
      latitude: 11,
      longitude: 22,
    });

    expect(obstacle.id).toBe("obstacle-1");
    expect(obstacle.name).toBe("禁行区");
    expect(obstacle.sideId).toBe("");
    expect(obstacle.radiusNm).toBe(10);
    expect(obstacle.obstacleType).toBe("no_go");
    expect(obstacle.active).toBe(true);
    expect(obstacle.movementPenalty).toBe(1);
    expect(obstacle.detectionPenalty).toBe(0);
    expect(obstacle.affectedDomains).toStrictEqual(["aircraft", "ship"]);
  });

  test("Game.loadScenario preserves backend obstacle snapshots", () => {
    const game = new Game(
      new Scenario({
        id: "empty",
        name: "Empty",
        startTime: 0,
        duration: 600,
      })
    );
    const snapshot = {
      currentSideId: "blue",
      selectedUnitId: "",
      mapView: game.mapView,
      currentScenario: {
        id: "scenario-1",
        name: "Obstacle Scenario",
        startTime: 0,
        currentTime: 0,
        duration: 600,
        sides: [{ id: "blue", name: "BLUE", totalScore: 0, color: "blue" }],
        timeCompression: 1,
        aircraft: [],
        airbases: [],
        facilities: [],
        ships: [],
        weapons: [],
        referencePoints: [],
        obstacles: [
          {
            id: "weather-zone",
            name: "恶劣天气区",
            className: "恶劣天气区",
            sideId: "blue",
            latitude: 11,
            longitude: 22,
            altitude: 0,
            radiusNm: 25,
            obstacleType: "weather",
            sideColor: "blue",
            active: true,
            movementPenalty: 0.25,
            detectionPenalty: 0.35,
            communicationPenalty: 0.15,
            affectedDomains: ["aircraft", "ship"],
            description: "天气约束",
          },
        ],
        missions: [],
        relationships: { hostiles: {}, allies: {} },
        doctrine: {},
      },
    };

    game.loadScenario(JSON.stringify(snapshot));

    const obstacle = game.currentScenario.getObstacle("weather-zone");
    expect(obstacle).toBeInstanceOf(Obstacle);
    expect(obstacle?.obstacleType).toBe("weather");
    expect(obstacle?.radiusNm).toBe(25);
    expect(obstacle?.movementPenalty).toBe(0.25);
    expect(obstacle?.detectionPenalty).toBe(0.35);
    expect(obstacle?.communicationPenalty).toBe(0.15);
  });
});
