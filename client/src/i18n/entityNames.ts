import i18n from "@/i18n";

// Centralized localization helpers for unit names / classes / sides.
// All return the original input when the locale has no translation, so
// switching to English (which leaves entity.* maps empty) shows raw names.

export function localizeSideName(name: string): string {
  if (!name) return "";
  return i18n.t(`entity.side.${name}`, { defaultValue: name });
}

export function localizeClassName(className: string): string {
  if (!className) return "";
  return i18n.t(`entity.class.${className}`, { defaultValue: className });
}

export function localizeAirbaseName(name: string): string {
  if (!name) return "";
  return i18n.t(`entity.airbase.${name}`, { defaultValue: name });
}

export function localizeWeaponName(name: string): string {
  if (!name) return "";
  const weaponLabels = (i18n.t("unitClass.weapon", {
    returnObjects: true,
    defaultValue: {},
  }) || {}) as Record<string, string>;
  if (weaponLabels[name]) return weaponLabels[name];
  const m = /^(.+?)\s*(#.+)?$/.exec(name);
  if (m && weaponLabels[m[1].trim()]) {
    return m[2]
      ? `${weaponLabels[m[1].trim()]} ${m[2]}`
      : weaponLabels[m[1].trim()];
  }
  return name;
}

// Unit names in scenarios usually look like "Beaver #1" or "Raptor #420".
// We try an exact match first; otherwise we strip the "#<n>" suffix and
// translate the callsign prefix, preserving the suffix unchanged.
export function localizeUnitName(name: string): string {
  if (!name) return "";
  const exact = i18n.t(`entity.name.${name}`, { defaultValue: "" });
  if (exact) return exact;
  const airbase = localizeAirbaseName(name);
  if (airbase !== name) return airbase;
  const m = /^([^#]+?)\s*(#.+)?$/.exec(name);
  if (m) {
    const prefix = m[1].trim();
    const suffix = m[2] ?? "";
    const translated = i18n.t(`entity.callsign.${prefix}`, {
      defaultValue: "",
    });
    if (translated) {
      return suffix ? `${translated} ${suffix}` : translated;
    }
  }
  return name;
}
