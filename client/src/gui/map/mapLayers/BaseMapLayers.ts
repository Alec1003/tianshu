import TileLayer from "ol/layer/Tile.js";
import { Projection, get as getProjection } from "ol/proj";
import OSM from "ol/source/OSM.js";
import TileJSON from "ol/source/TileJSON.js";
import XYZ from "ol/source/XYZ.js";
import { DEFAULT_OL_PROJECTION_CODE } from "@/utils/constants";

const defaultProjection = getProjection(DEFAULT_OL_PROJECTION_CODE);
const GAODE_VECTOR_TILE_URL =
  "https://webrd0{1-4}.is.autonavi.com/appmaptile?lang=zh_cn&size=1&scale=1&style=7&x={x}&y={y}&z={z}";

export default class BaseMapLayers {
  layers: (TileLayer<OSM> | TileLayer<TileJSON> | TileLayer<XYZ>)[];
  projection: Projection;
  currentLayerIndex: number;

  constructor(
    projection?: Projection,
    mapTilerBasicUrl?: string,
    mapTilerSatelliteUrl?: string,
    zIndex?: number
  ) {
    this.layers = [];
    if (mapTilerBasicUrl) {
      this.layers.push(this.createMapTilerBasicLayer(mapTilerBasicUrl, zIndex));
    }
    if (mapTilerSatelliteUrl) {
      this.layers.push(
        this.createMapTilerSatelliteLayer(mapTilerSatelliteUrl, zIndex)
      );
    }
    this.layers.push(this.createBaseGaodeLayer(zIndex));
    this.projection = projection ?? defaultProjection!;
    this.layers.forEach((layer) => layer.setZIndex(zIndex ?? -1));
    this.currentLayerIndex = this.layers.length - 1;
  }

  createBaseGaodeLayer = (zIndex?: number) => {
    const gaodeLayer = new TileLayer({
      source: new XYZ({
        url: GAODE_VECTOR_TILE_URL,
      }),
    });
    gaodeLayer.setZIndex(zIndex ?? -1);
    return gaodeLayer;
  };

  createMapTilerBasicLayer = (url: string, zIndex?: number) => {
    const mapTilerBasicLayer = new TileLayer({
      source: new OSM({
        url: url,
      }),
    });
    mapTilerBasicLayer.setZIndex(zIndex ?? -1);
    return mapTilerBasicLayer;
  };

  createMapTilerSatelliteLayer = (url: string, zIndex?: number) => {
    const mapTilerSatelliteSource = new TileJSON({
      url: url,
      tileSize: 512,
      crossOrigin: "anonymous",
    });
    const mapTilerSatelliteLayer = new TileLayer({
      source: mapTilerSatelliteSource,
    });
    mapTilerSatelliteLayer.setZIndex(zIndex ?? -1);
    return mapTilerSatelliteLayer;
  };

  toggleLayer = () => {
    this.currentLayerIndex = (this.currentLayerIndex + 1) % this.layers.length;
    this.layers.forEach((layer, index) => {
      if (index === this.currentLayerIndex) layer.setVisible(true);
      else layer.setVisible(false);
    });
  };
}
