import { describe, test, expect } from "vitest";
import Relationships from "@/game/Relationships";

describe("Relationships symmetry", () => {
  test("addHostile is symmetric in both directions", () => {
    const r = new Relationships({});
    r.addHostile("A", "B");
    expect(r.isHostile("A", "B")).toBe(true);
    expect(r.isHostile("B", "A")).toBe(true);
  });

  test("removeHostile clears both directions", () => {
    const r = new Relationships({});
    r.addHostile("A", "B");
    r.removeHostile("A", "B");
    expect(r.isHostile("A", "B")).toBe(false);
    expect(r.isHostile("B", "A")).toBe(false);
  });

  test("addAlly is symmetric in both directions", () => {
    const r = new Relationships({});
    r.addAlly("A", "B");
    expect(r.isAlly("A", "B")).toBe(true);
    expect(r.isAlly("B", "A")).toBe(true);
  });

  test("removeAlly clears both directions", () => {
    const r = new Relationships({});
    r.addAlly("A", "B");
    r.removeAlly("A", "B");
    expect(r.isAlly("A", "B")).toBe(false);
    expect(r.isAlly("B", "A")).toBe(false);
  });

  test("turning an ally into a hostile drops the alliance on both sides", () => {
    const r = new Relationships({});
    r.addAlly("A", "B");
    r.addHostile("A", "B");
    expect(r.isHostile("A", "B")).toBe(true);
    expect(r.isHostile("B", "A")).toBe(true);
    expect(r.isAlly("A", "B")).toBe(false);
    expect(r.isAlly("B", "A")).toBe(false);
  });

  test("addHostile is a no-op when sideId equals hostileId", () => {
    const r = new Relationships({});
    r.addHostile("A", "A");
    expect(r.isHostile("A", "A")).toBe(false);
  });

  test("updateRelationship mirrors hostiles and allies onto other sides", () => {
    const r = new Relationships({});
    r.updateRelationship("A", ["B", "C"], ["D"]);

    expect(r.isHostile("A", "B")).toBe(true);
    expect(r.isHostile("B", "A")).toBe(true);
    expect(r.isHostile("A", "C")).toBe(true);
    expect(r.isHostile("C", "A")).toBe(true);
    expect(r.isAlly("A", "D")).toBe(true);
    expect(r.isAlly("D", "A")).toBe(true);
  });

  test("updateRelationship removes the mirrored entry when a hostile is dropped", () => {
    const r = new Relationships({});
    r.updateRelationship("A", ["B", "C"], []);
    r.updateRelationship("A", ["B"], []);

    expect(r.isHostile("A", "C")).toBe(false);
    expect(r.isHostile("C", "A")).toBe(false);
    expect(r.isHostile("A", "B")).toBe(true);
    expect(r.isHostile("B", "A")).toBe(true);
  });

  test("updateRelationship deduplicates and drops self references", () => {
    const r = new Relationships({});
    r.updateRelationship("A", ["B", "B", "A", ""], ["C", "C", "A"]);

    expect(r.hostiles["A"]).toEqual(["B"]);
    expect(r.allies["A"]).toEqual(["C"]);
  });

  test("updateRelationship resolves conflicts by giving hostile priority", () => {
    const r = new Relationships({});
    r.updateRelationship("A", ["B"], ["B"]);

    expect(r.isHostile("A", "B")).toBe(true);
    expect(r.isAlly("A", "B")).toBe(false);
  });

  test("updateRelationship switching B from hostile to ally flips B's entry as well", () => {
    const r = new Relationships({});
    r.updateRelationship("A", ["B"], []);
    expect(r.isHostile("B", "A")).toBe(true);

    r.updateRelationship("A", [], ["B"]);
    expect(r.isHostile("B", "A")).toBe(false);
    expect(r.isAlly("B", "A")).toBe(true);
  });

  test("deleteSide purges the side from both sides of every relation", () => {
    const r = new Relationships({});
    r.addHostile("A", "B");
    r.addAlly("A", "C");
    r.deleteSide("A");

    expect(r.hostiles["A"]).toBeUndefined();
    expect(r.allies["A"]).toBeUndefined();
    expect(r.isHostile("B", "A")).toBe(false);
    expect(r.isAlly("C", "A")).toBe(false);
  });
});
