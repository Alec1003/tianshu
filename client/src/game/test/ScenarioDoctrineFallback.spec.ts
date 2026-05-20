import { describe, expect, test } from "vitest";

import Scenario from "@/game/Scenario";
import Side from "@/game/Side";
import Relationships from "@/game/Relationships";
import { DoctrineType } from "@/game/Doctrine";
import type Doctrine from "@/game/Doctrine";

// 回归：服务端历史上会把 doctrine 序列化成 `{}`，前端原本依赖
// `parameters.doctrine ?? getDefaultDoctrine()` 触发默认值，但 `{}` 是
// truthy，??不触发 → checkSideDoctrine 全部判 false → 红蓝静止不交战。
// 现在 Scenario 构造函数对空 doctrine / 缺 sideId 条目走默认条令兜底。

function makeSides() {
  return [
    new Side({ id: "blue-1", name: "BLUE", color: "blue" }),
    new Side({ id: "red-1", name: "RED", color: "red" }),
  ];
}

function makeScenario(doctrine?: Doctrine) {
  return new Scenario({
    id: "sc-1",
    name: "Doctrine Fallback Test",
    startTime: 0,
    currentTime: 0,
    duration: 600,
    sides: makeSides(),
    relationships: new Relationships({}),
    doctrine,
  });
}

describe("Scenario doctrine fallback", () => {
  test("undefined doctrine falls back to default for every side", () => {
    const sc = makeScenario(undefined);
    expect(
      sc.checkSideDoctrine("blue-1", DoctrineType.AIRCRAFT_ATTACK_HOSTILE)
    ).toBe(true);
    expect(
      sc.checkSideDoctrine("red-1", DoctrineType.SAM_ATTACK_HOSTILE)
    ).toBe(true);
  });

  test("empty {} doctrine falls back to default for every side", () => {
    const sc = makeScenario({} as Doctrine);
    expect(
      sc.checkSideDoctrine("blue-1", DoctrineType.AIRCRAFT_ATTACK_HOSTILE)
    ).toBe(true);
    expect(
      sc.checkSideDoctrine("red-1", DoctrineType.SHIP_ATTACK_HOSTILE)
    ).toBe(true);
  });

  test("partial doctrine backfills missing sides without overriding given ones", () => {
    const partial: Doctrine = {
      "blue-1": {
        [DoctrineType.AIRCRAFT_ATTACK_HOSTILE]: false,
        [DoctrineType.AIRCRAFT_CHASE_HOSTILE]: true,
        [DoctrineType.AIRCRAFT_RTB_WHEN_OUT_OF_RANGE]: false,
        [DoctrineType.AIRCRAFT_RTB_WHEN_STRIKE_MISSION_COMPLETE]: false,
        [DoctrineType.SAM_ATTACK_HOSTILE]: true,
        [DoctrineType.SHIP_ATTACK_HOSTILE]: true,
      },
    };
    const sc = makeScenario(partial);

    // 给定方按用户值
    expect(
      sc.checkSideDoctrine("blue-1", DoctrineType.AIRCRAFT_ATTACK_HOSTILE)
    ).toBe(false);
    // 缺失方按默认（全开交战）
    expect(
      sc.checkSideDoctrine("red-1", DoctrineType.AIRCRAFT_ATTACK_HOSTILE)
    ).toBe(true);
    expect(
      sc.checkSideDoctrine("red-1", DoctrineType.SAM_ATTACK_HOSTILE)
    ).toBe(true);
  });
});
