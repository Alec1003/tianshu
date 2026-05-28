export type CesiumBaseLayerKey =
  | "lightVector"
  | "darkMatter"
  | "satellite"
  | "sentinel";

export interface CesiumPlacement {
  type: "aircraft" | "ship" | "facility" | "airbase" | "referencePoint";
  className?: string;
}
