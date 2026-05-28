import Aircraft from "@/game/units/Aircraft";
import Weapon from "@/game/units/Weapon";

describe("Aircraft", () => {
  test("an Aircraft is instantiated correctly", () => {
    const testWeapon = new Weapon({
      id: "123456",
      name: "Sample Weapon",
      sideId: "sideId",
      className: "Sample Weapon",
      latitude: 0.0,
      longitude: 0.0,
      altitude: 10000.0,
      heading: 90.0,
      speed: 1000.0,
      currentFuel: 5000.0,
      maxFuel: 5000.0,
      fuelRate: 5000.0,
      range: 100,
      sideColor: "red",
      targetId: null,
      lethality: 0.5,
      maxQuantity: 20,
      currentQuantity: 20,
    });
    const testAircraft = new Aircraft({
      id: "12345",
      name: "F-16",
      sideId: "BLUE",
      className: "Fighter",
      latitude: 15,
      longitude: 20,
      altitude: 0.0,
      heading: 0,
      speed: 100,
      currentFuel: 100,
      maxFuel: 100,
      fuelRate: 10,
      range: 100,
      route: [
        [0, 0],
        [1, 1],
      ],
      sideColor: "blue",
      weapons: [testWeapon],
      homeBaseId: "homebase-1234",
      isTanker: true,
      fuelOffloadCapacity: 150000,
      fuelTransferRate: 100,
      refuelRange: 2,
    });
    expect(testAircraft.id).toBe("12345");
    expect(testAircraft.name).toBe("F-16");
    expect(testAircraft.sideId).toBe("BLUE");
    expect(testAircraft.className).toBe("Fighter");
    expect(testAircraft.latitude).toBe(15);
    expect(testAircraft.longitude).toBe(20);
    expect(testAircraft.altitude).toBe(0.0);
    expect(testAircraft.heading).toBe(0);
    expect(testAircraft.speed).toBe(100);
    expect(testAircraft.currentFuel).toBe(100);
    expect(testAircraft.maxFuel).toBe(100);
    expect(testAircraft.fuelRate).toBe(10);
    expect(testAircraft.range).toBe(100);
    expect(testAircraft.sideColor).toBe("blue");
    expect(testAircraft.route.length).toBe(2);
    expect(testAircraft.route[0]).toStrictEqual([0, 0]);
    expect(testAircraft.route[1]).toStrictEqual([1, 1]);
    expect(testAircraft.weapons.length).toBe(1);
    expect(testAircraft.weapons[0]).toBe(testWeapon);
    expect(testAircraft.homeBaseId).toBe("homebase-1234");
    expect(testAircraft.selected).toBe(false);
    expect(testAircraft.rtb).toBe(false);
    expect(testAircraft.isTanker).toBe(true);
    expect(testAircraft.fuelOffloadCapacity).toBe(150000);
    expect(testAircraft.fuelTransferRate).toBe(100);
    expect(testAircraft.refuelRange).toBe(2);
  });

  test("an electronic warfare aircraft preserves jamming settings", () => {
    const testAircraft = new Aircraft({
      id: "ew-1",
      name: "Growler",
      sideId: "BLUE",
      className: "EA-18G Growler",
      latitude: 15,
      longitude: 20,
      altitude: 10000,
      heading: 90,
      speed: 500,
      currentFuel: 1000,
      maxFuel: 1000,
      fuelRate: 100,
      range: 120,
      isElectronicWarfare: true,
      jammingRange: 150,
      jammingStrength: 1,
      jammingModes: ["radar"],
      communicationDisruption: 0.3,
    });

    expect(testAircraft.isElectronicWarfare).toBe(true);
    expect(testAircraft.jammingRange).toBe(150);
    expect(testAircraft.jammingStrength).toBe(0.85);
    expect(testAircraft.jammingModes).toStrictEqual(["radar"]);
    expect(testAircraft.communicationDisruption).toBe(0.3);
  });

  test("getTotalWeaponQuantity returns the correct number of weapons on an Aircraft", () => {
    const testWeapon1 = new Weapon({
      id: "123456",
      name: "Sample Weapon",
      sideId: "sideId",
      className: "Sample Weapon",
      latitude: 0.0,
      longitude: 0.0,
      altitude: 10000.0,
      heading: 90.0,
      speed: 1000.0,
      currentFuel: 5000.0,
      maxFuel: 5000.0,
      fuelRate: 5000.0,
      range: 100,
      sideColor: "red",
      targetId: null,
      lethality: 0.5,
      maxQuantity: 20,
      currentQuantity: 20,
    });
    const testWeapon2 = new Weapon({
      id: "123456",
      name: "Sample Weapon",
      sideId: "sideId",
      className: "Sample Weapon",
      latitude: 0.0,
      longitude: 0.0,
      altitude: 10000.0,
      heading: 90.0,
      speed: 1000.0,
      currentFuel: 5000.0,
      maxFuel: 5000.0,
      fuelRate: 5000.0,
      range: 100,
      sideColor: "red",
      targetId: null,
      lethality: 0.5,
      maxQuantity: 30,
      currentQuantity: 30,
    });
    const testAircraft = new Aircraft({
      id: "12345",
      name: "F-16",
      sideId: "BLUE",
      className: "Fighter",
      latitude: 15,
      longitude: 20,
      altitude: 0.0,
      heading: 0,
      speed: 100,
      currentFuel: 100,
      maxFuel: 100,
      fuelRate: 10,
      range: 100,
      weapons: [testWeapon1, testWeapon2],
    });
    expect(testAircraft.getTotalWeaponQuantity()).toBe(50);
  });
});
