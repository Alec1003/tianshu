import BaseMapLayers from "@/gui/map/mapLayers/BaseMapLayers";

describe("BaseMapLayers", () => {
  test("uses Gaode tiles for the default base layer", () => {
    const baseLayers = new BaseMapLayers();
    const defaultLayer = baseLayers.layers[baseLayers.layers.length - 1];
    const source = defaultLayer.getSource() as { getUrls?: () => string[] };
    const urls = source.getUrls?.() ?? [];

    expect(urls.length).toBeGreaterThan(0);
    expect(urls[0]).toContain("autonavi.com");
  });
});
