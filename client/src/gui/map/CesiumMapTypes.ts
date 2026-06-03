export type CesiumBaseLayerKey =
  | "lightVector"
  | "darkMatter"
  | "arcgisImagery"
  | "satellite"
  | "sentinel";

export interface CesiumPlacement {
  type: "aircraft" | "ship" | "facility" | "airbase" | "referencePoint";
  className?: string;
}
