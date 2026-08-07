"""
CesiumJS 专业 3D 可视化输出。

在 WGS84 地球上展示平台、目标、路径、威胁场和禁飞区。
支持椭圆柱体威胁 (CAP 巡逻区)、锥体地面裁剪、路径威胁分段着色。
"""

import json
import math
from pathlib import Path
from typing import List

from ..grid import Grid
from ..core.geo import local_to_llh, radar_horizon
from ..core.types import PathResult
from ..io import Scenario


PLATFORM_COLORS = [
    "#1b9e77",
    "#d95f02",
    "#7570b3",
    "#e7298a",
    "#66a61e",
    "#e6ab02",
    "#a6761d",
]


def _threat_color(val):
    if val <= 1e-6:
        return "#10b981"
    if val <= 0.01:
        return "#34d399"
    if val <= 0.1:
        return "#facc15"
    if val <= 0.3:
        return "#f97316"
    if val <= 0.5:
        return "#ef4444"
    return "#dc2626"


def _cone_ground_params(apex_up_km, dir_z, max_range_km, angle_deg):
    if dir_z >= -1e-9 or apex_up_km <= 0:
        bottom_r = max_range_km * math.tan(math.radians(angle_deg))
        return (max_range_km, bottom_r, None)
    t_ground = abs(apex_up_km / dir_z) if abs(dir_z) > 1e-9 else float("inf")
    visible_len = min(max_range_km, t_ground)
    bottom_r = visible_len * math.tan(math.radians(angle_deg))
    surface_r = None
    if t_ground <= max_range_km and t_ground > 1e-6:
        if t_ground <= radar_horizon(apex_up_km, 0.0):
            surface_r = t_ground * math.tan(math.radians(angle_deg))
    return (visible_len, bottom_r, surface_r)


def _sphere_surface_footprint_km(center_up_km, radius_km):
    geometric_r = math.sqrt(max(0.0, radius_km**2 - center_up_km**2))
    visible_r = radar_horizon(center_up_km, 0.0)
    effective_r = min(geometric_r, visible_r)
    return effective_r if effective_r > 1e-3 else None


def _earth_texture_data_uri():
    tex = Path(__file__).with_name("earth_texture.jpg")
    if tex.exists():
        import base64

        with open(tex, "rb") as f:
            return "data:image/jpeg;base64," + base64.b64encode(f.read()).decode()
    return ""


def _serialize_refuel_segments(refuel_segments_map):
    result = []
    for key, segments in refuel_segments_map.items():
        pid = key.split("->")[0] if "->" in key else key
        for rs in segments:
            if hasattr(rs, "start_position_llh"):
                start_pos = rs.start_position_llh
                end_pos = rs.end_position_llh
                adjusted = rs.adjusted
                platform_id = rs.platform_id
                refuel_distance_km = rs.refuel_distance_km
            else:
                sp = rs.get("start_position", [0, 0, 0])
                ep = rs.get("end_position", [0, 0, 0])
                start_pos = (sp[0], sp[1], sp[2])
                end_pos = (ep[0], ep[1], ep[2])
                adjusted = rs.get("adjusted", False)
                platform_id = rs.get("platform_id", pid)
                refuel_distance_km = rs.get("refuel_distance_km", 0)
            result.append(
                {
                    "platform_id": platform_id,
                    "start_position": list(start_pos),
                    "end_position": list(end_pos),
                    "adjusted": adjusted,
                    "refuel_distance_km": refuel_distance_km,
                }
            )
    return result


def _build_payload(scenario, grid, results, title, refuel_segments_map=None):
    groups = {}
    for r in results:
        groups.setdefault((r.platform_id, r.target_id), []).append(r)

    paths = []
    color_idx = 0
    for (pid, tid), group in groups.items():
        group.sort(key=lambda item: item.cost)
        color = PLATFORM_COLORS[color_idx % len(PLATFORM_COLORS)]
        for rank, result in enumerate(group):
            wps = [[round(v, 6) for v in wp] for wp in result.waypoints_llh]

            segment_colors = []
            for seg in result.segment_details:
                exp = seg.get("threat_exposure", 0)
                seg_len = seg.get("segment_cost", 0)
                n = exp / max(seg_len, 1.0) if seg_len > 0 else exp
                segment_colors.append(_threat_color(n))

            wp_threat_raw = (
                [round(wd.get("threat_cost", 0), 6) for wd in result.waypoint_details]
                if result.waypoint_details
                else []
            )
            wp_threat = wp_threat_raw if wp_threat_raw else [0.0] * len(wps)

            cum_dist = [0.0]
            for i in range(1, len(wps)):
                lon1, lat1, alt1 = wps[i - 1]
                lon2, lat2, alt2 = wps[i]
                dlon = (
                    (lon2 - lon1) * 111.32 * math.cos(math.radians((lat1 + lat2) / 2))
                )
                dlat = (lat2 - lat1) * 111.32
                dalt = (alt2 - alt1) / 1000.0
                cum_dist.append(cum_dist[-1] + math.sqrt(dlon**2 + dlat**2 + dalt**2))

            alt_profile = [
                [round(cum_dist[i], 2), wps[i][2], wp_threat[i]]
                for i in range(len(wps))
            ]

            paths.append(
                {
                    "routeId": f"{pid}-{tid}-{rank}",
                    "platform_id": pid,
                    "target_id": tid,
                    "direction": [result.direction[0], result.direction[1]],
                    "direction_label": result.direction_label,
                    "control_point": list(result.control_point_llh)
                    if result.control_point_llh
                    else None,
                    "control_point_label": result.control_point_label,
                    "control_point_kind": result.control_point_kind,
                    "cost": round(result.cost, 2),
                    "threat_exposure": round(result.threat_exposure, 4),
                    "arrival_angle": list(result.arrival_angle),
                    "color": color,
                    "rank": rank,
                    "waypoints": wps,
                    "segment_colors": segment_colors,
                    "wp_threat_costs": wp_threat,
                    "alt_profile": alt_profile,
                }
            )
        color_idx += 1

    spheres_data = []
    for s in scenario.threat_field.spheres:
        center_llh = list(local_to_llh(*s.center, scenario.ref_lon, scenario.ref_lat))
        surface_c = list(
            local_to_llh(
                s.center[0], s.center[1], 0.0, scenario.ref_lon, scenario.ref_lat
            )
        )
        fp = _sphere_surface_footprint_km(s.center[2], s.radius)
        spheres_data.append(
            {
                "id": s.id or "sphere",
                "center": center_llh,
                "center_up_km": s.center[2],
                "radius_m": s.radius * 1000.0,
                "threat_level": s.threat_level,
                "surface_center": surface_c,
                "surface_radius_m": fp * 1000.0 if fp else 0.0,
                "horizon_km": radar_horizon(s.center[2], 0.0),
                "has_footprint": fp is not None and fp > 0.01,
            }
        )

    cylinders_data = []
    for cy in scenario.threat_field.cylinders:
        c = list(
            local_to_llh(
                cy.center_2d[0],
                cy.center_2d[1],
                cy.height / 2.0,
                scenario.ref_lon,
                scenario.ref_lat,
            )
        )
        cylinders_data.append(
            {
                "id": cy.id or "cylinder",
                "center": c,
                "radius_m": cy.radius * 1000.0,
                "height_m": cy.height * 1000.0,
                "threat_level": cy.threat_level,
            }
        )

    ec_data = []
    for ec in scenario.threat_field.elliptic_cylinders:
        c = list(
            local_to_llh(
                ec.center_2d[0],
                ec.center_2d[1],
                ec.height / 2.0,
                scenario.ref_lon,
                scenario.ref_lat,
            )
        )
        ec_data.append(
            {
                "id": ec.id or "elliptic_cylinder",
                "center": c,
                "semi_major_m": ec.semi_major * 1000.0,
                "semi_minor_m": ec.semi_minor * 1000.0,
                "azimuth_deg": ec.azimuth_deg,
                "height_m": ec.height * 1000.0,
                "threat_level": ec.threat_level,
            }
        )

    nfz_data = []
    for nfz in scenario.threat_field.no_fly_zones:
        c = list(
            local_to_llh(
                nfz.center_2d[0],
                nfz.center_2d[1],
                nfz.height / 2.0,
                scenario.ref_lon,
                scenario.ref_lat,
            )
        )
        nfz_data.append(
            {
                "id": nfz.id or "nfz",
                "center": c,
                "radius_m": nfz.radius * 1000.0,
                "height_m": nfz.height * 1000.0,
            }
        )

    cones_data = []
    for cone in scenario.threat_field.cones:
        apex_llh = list(local_to_llh(*cone.apex, scenario.ref_lon, scenario.ref_lat))
        apex_up = cone.apex[2]
        dir_z = cone.direction[2]
        vl, br, sr = _cone_ground_params(
            apex_up, dir_z, cone.max_range_km, cone.angle_deg
        )
        surface_llh = None
        if sr is not None and dir_z < -1e-9:
            tg = abs(apex_up / dir_z)
            se = cone.apex[0] + cone.direction[0] * tg
            sn = cone.apex[1] + cone.direction[1] * tg
            surface_llh = list(
                local_to_llh(se, sn, 0.0, scenario.ref_lon, scenario.ref_lat)
            )
        cones_data.append(
            {
                "id": cone.id or "cone",
                "apex": apex_llh,
                "apex_up_km": apex_up,
                "direction_enu": list(cone.direction),
                "direction_z": dir_z,
                "max_range_m": cone.max_range_km * 1000.0,
                "angle_deg": cone.angle_deg,
                "threat_level": cone.threat_level,
                "visible_length_m": vl * 1000.0,
                "bottom_radius_m": br * 1000.0,
                "surface_footprint_radius_m": sr * 1000.0 if sr else 0.0,
                "surface_center_llh": surface_llh,
                "hits_ground": sr is not None,
            }
        )

    return {
        "title": title,
        "scenario_name": scenario.name,
        "ref_point": [scenario.ref_lon, scenario.ref_lat],
        "earth_texture_data_uri": _earth_texture_data_uri(),
        "summary": {
            "platform_count": len(scenario.platforms),
            "target_count": len(scenario.targets),
            "waypoint_count": len(scenario.waypoints),
            "path_count": len(paths),
            "sphere_count": len(spheres_data),
            "cone_count": len(cones_data),
            "cylinder_count": len(cylinders_data),
            "elliptic_cylinder_count": len(ec_data),
            "nfz_count": len(nfz_data),
        },
        "platforms": [
            {"id": p.id, "type": p.type, "position": list(p.position_llh)}
            for p in scenario.platforms
        ],
        "targets": [
            {
                "id": t.id,
                "position": list(t.position_llh),
                "arrival_radius_km": t.arrival_radius_km,
            }
            for t in scenario.targets
        ],
        "waypoints": [
            {
                "id": wp.id,
                "position": list(wp.position_llh),
            }
            for wp in scenario.waypoints
        ],
        "paths": paths,
        "refuel_segments": _serialize_refuel_segments(refuel_segments_map)
        if refuel_segments_map
        else [],
        "threats": {
            "spheres": spheres_data,
            "cylinders": cylinders_data,
            "elliptic_cylinders": ec_data,
            "no_fly_zones": nfz_data,
            "cones": cones_data,
        },
    }


def plot_scenario_3d(
    scenario,
    grid,
    results,
    output_path="route_plan_3d.html",
    title=None,
    refuel_segments_map=None,
):
    payload = _build_payload(
        scenario,
        grid,
        results,
        title or f"路径规划 — {scenario.name}",
        refuel_segments_map,
    )
    html = _build_html(payload)
    Path(output_path).write_text(html, encoding="utf-8")
    print(f"  Cesium 3D 可视化已保存: {output_path}")


def _build_html(payload):
    payload_json = json.dumps(payload, ensure_ascii=False)
    return _HTML_TEMPLATE.replace("{payload_json}", payload_json)


_HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8"/><meta name="viewport" content="width=device-width,initial-scale=1.0"/>
<title>路径规划可视化</title>
<link href="https://cesium.com/downloads/cesiumjs/releases/1.120/Build/Cesium/Widgets/widgets.css" rel="stylesheet"/>
<style>
:root{--bg:#060e1a;--panel:rgba(8,16,28,0.88);--panel-hdr:rgba(12,22,38,0.94);
--line:rgba(140,190,230,0.12);--line-focus:rgba(140,190,230,0.22);
--text:#e2eaf2;--muted:#7a94b0;--accent:#60a5fa;--danger:#f87171;--good:#34d399;
--orange:#fb923c;--cyan:#22d3ee;--purple:#c084fc;--teal:#2dd4bf;}
html,body{margin:0;width:100%;height:100%;overflow:hidden;
background:radial-gradient(ellipse at 20% 20%,rgba(24,64,120,.22),transparent 50%),
radial-gradient(ellipse at 80% 80%,rgba(12,60,100,.16),transparent 50%),
linear-gradient(180deg,#030a14 0%,#071320 50%,#040c18 100%);
font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Hiragino Sans GB","Microsoft YaHei",sans-serif;
color:var(--text);font-size:12px;line-height:1.5;-webkit-font-smoothing:antialiased;}
#app{position:relative;width:100%;height:100%;}
#cesiumContainer{width:100%;height:100%;}
.panel{position:absolute;z-index:10;background:var(--panel);border:1px solid var(--line);
box-shadow:0 16px 48px rgba(0,0,0,.4);backdrop-filter:blur(20px);-webkit-backdrop-filter:blur(20px);}
#overlay{top:14px;left:14px;width:312px;border-radius:14px;overflow:hidden;}
#overlayHeader{padding:12px 16px 10px;
background:linear-gradient(135deg,rgba(30,80,140,.28),rgba(8,18,32,.06)),
linear-gradient(180deg,rgba(255,255,255,.03),transparent);
border-bottom:1px solid var(--line);}
#overlayHeader .eyebrow{margin:0 0 4px;color:var(--accent);font-size:10px;font-weight:700;letter-spacing:.1em;}
#overlayHeader h1{margin:0;font-size:17px;font-weight:700;letter-spacing:-.01em;}
#overlayHeader .subtitle{margin:6px 0 0;color:var(--muted);font-size:11px;}
#overlayBody{padding:10px 14px;max-height:calc(100vh - 190px);overflow-y:auto}
#overlayBody::-webkit-scrollbar{width:3px}
#overlayBody::-webkit-scrollbar-thumb{background:var(--line);border-radius:2px}
.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:5px;margin-bottom:10px}
.statCard{padding:8px 6px 6px;border-radius:8px;border:1px solid var(--line);background:rgba(255,255,255,.025);text-align:center}
.statCard .val{font-size:16px;font-weight:700;line-height:1.1;display:block}
.statCard .lbl{font-size:9px;color:var(--muted);margin-top:2px}
.section{margin-top:10px;padding-top:10px;border-top:1px solid var(--line)}
.section:first-child{margin-top:0;padding-top:0;border-top:0}
.sectionTitle{margin:0 0 7px;color:var(--muted);font-size:10px;font-weight:700;letter-spacing:.06em}
.buttonGrid{display:flex;flex-wrap:wrap;gap:5px}
button{padding:6px 10px;color:var(--text);font:inherit;font-size:11px;font-weight:600;
background:linear-gradient(180deg,rgba(40,80,140,.7),rgba(18,44,80,.85));
border:1px solid rgba(120,170,220,.18);border-radius:8px;cursor:pointer;
transition:all .15s}
button:hover{transform:translateY(-1px);
background:linear-gradient(180deg,rgba(55,105,175,.85),rgba(25,58,108,.92));
border-color:rgba(150,200,240,.3)}
.ghost{background:rgba(255,255,255,.04);border-color:var(--line-focus)}
.ghost:hover{background:rgba(255,255,255,.07)}
.toggleGrid{display:grid;grid-template-columns:repeat(3,1fr);gap:4px}
.toggleChip{display:flex;align-items:center;gap:5px;padding:6px 7px;border-radius:7px;
border:1px solid var(--line);background:rgba(255,255,255,.025);color:var(--muted);font-size:10px;cursor:pointer;
transition:all .12s}
.toggleChip:has(input:checked){border-color:var(--accent);color:var(--text)}
.toggleChip input{accent-color:var(--accent);margin:0;transform:scale(.8)}
.threatList{display:grid;gap:4px;max-height:180px;overflow:auto}
.threatList::-webkit-scrollbar{width:3px}
.threatList::-webkit-scrollbar-thumb{background:var(--line);border-radius:2px}
.threatItem{display:grid;grid-template-columns:auto 1fr auto;gap:6px;align-items:center;
padding:6px 8px;border-radius:7px;border:1px solid var(--line);background:rgba(255,255,255,.02)}
.threatItem label{font-size:11px;display:flex;align-items:center;gap:5px;cursor:pointer;flex:1}
.threatItem input{accent-color:var(--accent);transform:scale(.8)}
.badge{justify-self:end;padding:2px 6px;border-radius:99px;font-size:8px;font-weight:700;letter-spacing:.06em}
.badge-sphere{background:rgba(248,113,113,.12);color:var(--danger)}
.badge-cone{background:rgba(251,146,60,.12);color:var(--orange)}
.badge-cyl{background:rgba(56,189,248,.12);color:#38bdf8}
.badge-ellip{background:rgba(45,212,191,.12);color:var(--teal)}
.badge-nfz{background:rgba(192,132,252,.12);color:var(--purple)}
.legendList{display:grid;gap:3px}
.legendItem{display:flex;align-items:center;gap:8px;padding:5px 8px;border-radius:6px}
.legendSwatch{width:8px;height:8px;border-radius:50%;flex-shrink:0;box-shadow:0 0 0 2px rgba(255,255,255,.06)}
.legendText{font-size:10px;color:var(--muted);line-height:1.3}
.legendText strong{display:block;color:var(--text);font-size:11px;font-weight:600}
#routePanel{top:14px;right:14px;width:300px;max-height:calc(100vh-28px);border-radius:14px;overflow:hidden;display:flex;flex-direction:column}
#routePanelHeader{padding:12px 14px 10px;background:var(--panel-hdr);border-bottom:1px solid var(--line)}
#routePanelHeader h2{margin:0;font-size:14px;font-weight:700}
#routePanelHeader .sub{margin:4px 0 0;color:var(--muted);font-size:10px}
#routeList{padding:8px 10px;overflow:auto;flex:1}
#routeList::-webkit-scrollbar{width:3px}
#routeList::-webkit-scrollbar-thumb{background:var(--line);border-radius:2px}
.routeCard{padding:9px 10px;margin-bottom:4px;border-radius:8px;border:1px solid var(--line);
background:rgba(255,255,255,.015);cursor:pointer;transition:all .15s}
.routeCard:hover{background:rgba(255,255,255,.04);border-color:var(--line-focus)}
.routeCard.sel{border-color:var(--accent);background:rgba(96,165,250,.06)}
.routeCard .rhead{display:flex;align-items:center;gap:7px;margin-bottom:3px}
.routeCard .rdot{width:8px;height:8px;border-radius:50%;flex-shrink:0}
.routeCard .rname{font-size:11px;font-weight:600}
.routeCard .rmode{font-size:9px;padding:1px 5px;border-radius:3px;font-weight:600;flex-shrink:0}
.mode-launch{background:rgba(192,132,252,.15);color:var(--purple)}
.mode-anchor{background:rgba(96,165,250,.15);color:var(--accent)}
.mode-direct{background:rgba(52,211,153,.15);color:var(--good)}
.routeCard .rinfo{display:grid;grid-template-columns:1fr 1fr;gap:1px 12px;font-size:10px;color:var(--muted)}
.routeCard .rbar{display:flex;gap:2px;margin-top:5px;height:3px;border-radius:2px;overflow:hidden}
.routeCard .rseg{flex:1;border-radius:1px}
#hud{position:absolute;left:14px;bottom:14px;z-index:9;padding:8px 12px;border-radius:10px;
border:1px solid var(--line);background:rgba(8,16,28,.72);backdrop-filter:blur(14px);
color:var(--muted);font-size:10px;line-height:1.6}
#hud strong{color:var(--text)}
#hud kbd{display:inline-block;padding:1px 5px;border-radius:4px;border:1px solid var(--line-focus);
background:rgba(255,255,255,.04);font-family:inherit;font-size:9px;margin:0 2px}
#profilePanel{position:absolute;left:340px;right:328px;bottom:12px;height:130px;z-index:11;
border-radius:10px;border:1px solid var(--line);background:var(--panel-hdr);
backdrop-filter:blur(18px);display:none}
#profilePanel.show{display:block}
#profilePanel .phdr{display:flex;align-items:center;justify-content:space-between;padding:5px 10px;
border-bottom:1px solid var(--line);font-size:10px;font-weight:600}
#profilePanel .pclose{cursor:pointer;opacity:.4;font-size:15px;line-height:1}
#profilePanel .pclose:hover{opacity:1}
#profileCanvas{width:100%;height:calc(100% - 28px)}
@media(max-width:1080px){#overlay{width:280px}#routePanel{width:260px}#profilePanel{left:306px;right:286px}}
@media(max-width:860px){#overlay{width:260px;left:8px;top:8px}#routePanel{width:240px;right:8px;top:auto;bottom:8px;max-height:44%}#profilePanel{left:8px;right:8px;bottom:8px}}
</style>
</head>
<body>
<div id="app">
<div id="cesiumContainer"></div>

<section id="overlay" class="panel">
<div id="overlayHeader">
<div class="eyebrow">任务场景</div>
<h1>路径规划</h1>
<div class="subtitle">多方向进入 · 威胁规避 · 禁飞区绕行</div>
</div>
<div id="overlayBody">
<div class="stats" id="statGrid"></div>
<div class="section">
<div class="sectionTitle">视角预设</div>
<div class="buttonGrid" id="cameraPresets"></div>
</div>
<div class="section">
<div class="sectionTitle">图层控制</div>
<div class="toggleGrid" id="layerToggles"></div>
</div>
<div class="section">
<div class="sectionTitle">图例说明</div>
<div class="legendList" id="legend"></div>
</div>
<div class="section">
<div class="sectionTitle">威胁开关</div>
<div class="threatList" id="threatToggles"></div>
</div>
</div>
</section>

<aside id="routePanel" class="panel">
<div id="routePanelHeader">
<div style="display:flex;align-items:center;justify-content:space-between">
<h2 id="routePanelTitle">航线清单</h2>
<button id="showAllBtn" class="ghost" style="display:none;padding:3px 8px;font-size:10px">显示全部</button>
</div>
<div class="sub" id="routePanelSub">点击航线查看详情与高度剖面</div>
</div>
<div id="routeList"></div>
</aside>

<div id="profilePanel">
<div class="phdr">
<span id="profileTitle">高度剖面</span>
<span class="pclose" id="profileClose">&times;</span>
</div>
<canvas id="profileCanvas"></canvas>
</div>

<div id="hud">
<div><strong>操作说明</strong></div>
<div><kbd>左键拖拽</kbd> 旋转 &nbsp; <kbd>右键拖拽</kbd> 平移 &nbsp; <kbd>滚轮</kbd> 缩放</div>
<div><kbd>Ctrl+左键</kbd> 倾斜视角 &nbsp; <kbd>双击路线</kbd> 聚焦航线</div>
</div>
</div>

<script src="https://cesium.com/downloads/cesiumjs/releases/1.120/Build/Cesium/Cesium.js"></script>
<script>
(function(){
var DATA={payload_json};
var PLATFORM_COLORS=['#1b9e77','#d95f02','#7570b3','#e7298a','#66a61e','#e6ab02','#a6761d'];

// ============================================================
// Cesium 初始化
// ============================================================
var viewer=new Cesium.Viewer('cesiumContainer',{
animation:false,timeline:false,geocoder:false,
homeButton:false,baseLayerPicker:false,sceneModePicker:false,
navigationHelpButton:false,fullscreenButton:true,
selectionIndicator:false,infoBox:false,
terrainProvider:new Cesium.EllipsoidTerrainProvider(),
imageryProvider:DATA.earth_texture_data_uri
?new Cesium.SingleTileImageryProvider({url:DATA.earth_texture_data_uri})
:new Cesium.OpenStreetMapImageryProvider({url:'https://tile.openstreetmap.org/'}),
});
viewer.scene.globe.enableLighting=true;
viewer.scene.skyAtmosphere.show=true;
viewer.scene.fog.enabled=true;
viewer.scene.globe.depthTestAgainstTerrain=true;
viewer.scene.globe.baseColor=Cesium.Color.fromCssColorString('#16324d');
viewer.scene.screenSpaceCameraController.minimumZoomDistance=500;
viewer.scene.screenSpaceCameraController.tiltEventTypes=[
Cesium.CameraEventType.MIDDLE_DRAG,Cesium.CameraEventType.PINCH,
{eventType:Cesium.CameraEventType.LEFT_DRAG,modifier:Cesium.KeyboardEventModifier.CTRL},
{eventType:Cesium.CameraEventType.RIGHT_DRAG,modifier:Cesium.KeyboardEventModifier.CTRL},
];

function hexC(h,a){return Cesium.Color.fromCssColorString(h).withAlpha(a||1);}
function dPt(lon,lat,alt){return Cesium.Cartesian3.fromDegrees(lon,lat,alt||0);}
function lerp(a,b,t){return a+(b-a)*t;}
function clamp(v,min,max){return Math.max(min,Math.min(max,v));}
function buildCurved(wps){
if(!wps||wps.length<2)return[];
var out=[];
for(var i=0;i<wps.length-1;i++){
var a=wps[i],b=wps[i+1];
var sameLL=Math.abs(a[0]-b[0])<1e-9&&Math.abs(a[1]-b[1])<1e-9;
if(sameLL){
var vs=Math.max(2,Math.ceil(Math.abs((b[2]||0)-(a[2]||0))/1000));
for(var vi=0;vi<=vs;vi++){
if(i>0&&vi===0)continue;
out.push(a[0],a[1],lerp(a[2]||0,b[2]||0,vi/vs));
}
continue;
}
var s=Cesium.Cartographic.fromDegrees(a[0],a[1],a[2]||0);
var e=Cesium.Cartographic.fromDegrees(b[0],b[1],b[2]||0);
var geo=new Cesium.EllipsoidGeodesic(s,e);
var sd=Math.max(geo.surfaceDistance||0,1);
var ad=Math.abs((b[2]||0)-(a[2]||0));
var steps=Math.max(8,Math.ceil(sd/40000),Math.ceil(ad/1000));
for(var si=0;si<=steps;si++){
if(i>0&&si===0)continue;
var t1=si/steps;
var c=geo.interpolateUsingFraction(clamp(t1,0,1));
out.push(c.longitude*Cesium.Math.DEGREES_PER_RADIAN,c.latitude*Cesium.Math.DEGREES_PER_RADIAN,lerp(a[2]||0,b[2]||0,t1));
}
}
return out;
}

// ============================================================
// 图层注册
// ============================================================
var L={paths:[],pathGlow:[],shadows:[],targets:[],threats:[]};
var tById=new Map();
var routeMap=new Map();
function rL(k,e){if(Array.isArray(L[k]))L[k].push(e);}
function sV(k,v){(L[k]||[]).forEach(function(e){if(e&&typeof e.show!=='undefined')e.show=v;});}
var isoRid=null;
var layerStates={paths:true,pathGlow:false,shadows:true,targets:true,threats:true};
function applyVisibility(){
var ps=layerStates.paths,gs=layerStates.pathGlow,ss=layerStates.shadows,ts=layerStates.targets,ths=layerStates.threats;
var allRouteMarkers=new Set();
routeMap.forEach(function(e){e.markers.forEach(function(m){allRouteMarkers.add(m);});});
L.targets.forEach(function(e){if(!allRouteMarkers.has(e)&&e&&typeof e.show!=='undefined')e.show=ts;});
L.threats.forEach(function(e){if(e&&typeof e.show!=='undefined')e.show=ths;});
routeMap.forEach(function(entry,rid){
var show=!isoRid||isoRid===rid;
entry.segEnts.forEach(function(e){if(e&&typeof e.show!=='undefined')e.show=ps&&show;});
if(entry.glowEnt)entry.glowEnt.show=gs&&show;
if(entry.shEnt)entry.shEnt.show=ss&&show;
entry.markers.forEach(function(e){if(e&&typeof e.show!=='undefined')e.show=ts&&show;});
});
}

// ============================================================
// 场景统计
// ============================================================
var sg=document.getElementById('statGrid');
[
['平台',DATA.summary.platform_count],
['目标',DATA.summary.target_count],
['Waypoint',DATA.summary.waypoint_count],
['航线',DATA.summary.path_count],
['球体',DATA.summary.sphere_count],
['锥体',DATA.summary.cone_count],
['圆柱',DATA.summary.cylinder_count],
['椭圆柱',DATA.summary.elliptic_cylinder_count],
['禁飞区',DATA.summary.nfz_count],
].forEach(function(a){
var d=document.createElement('div');d.className='statCard';
d.innerHTML='<span class="val">'+a[1]+'</span><span class="lbl">'+a[0]+'</span>';
sg.appendChild(d);
});

// ============================================================
// 视角预设
// ============================================================
function cBounds(){
var a=[];
DATA.platforms.forEach(function(p){a.push(dPt(p.position[0],p.position[1],p.position[2]));});
DATA.targets.forEach(function(t){a.push(dPt(t.position[0],t.position[1],t.position[2]));});
DATA.paths.forEach(function(p){p.waypoints.forEach(function(w){a.push(dPt(w[0],w[1],w[2]));});});
return a.length?Cesium.BoundingSphere.fromPoints(a):null;
}
function fly(hdg,pitch,scale){
var b=cBounds();if(!b)return;
viewer.camera.flyToBoundingSphere(b,{duration:1,
offset:new Cesium.HeadingPitchRange(Cesium.Math.toRadians(hdg),Cesium.Math.toRadians(pitch),b.radius*scale)});
}
var cp=document.getElementById('cameraPresets');
[
['俯视',0,-89,1.8],['斜45°',45,-35,2.4],['地平线',90,-5,3.2],['重置',20,-45,2.2]
].forEach(function(a){
var btn=document.createElement('button');
btn.textContent=a[0];
btn.addEventListener('click',function(){fly(a[1],a[2],a[3]);});
cp.appendChild(btn);
});

// ============================================================
// 图层开关
// ============================================================
var lt=document.getElementById('layerToggles');
[
['航线','paths',true],['辉光','pathGlow',false],['投影','shadows',true],
['平台/目标','targets',true],['威胁体','threats',true],
].forEach(function(a){
var chip=document.createElement('label');chip.className='toggleChip';
var cb=document.createElement('input');
cb.type='checkbox';cb.checked=a[2];
cb.addEventListener('change',function(){layerStates[a[1]]=cb.checked;applyVisibility();});
chip.appendChild(cb);chip.appendChild(document.createTextNode(a[0]));
lt.appendChild(chip);
});

// ============================================================
// 图例
// ============================================================
var leg=document.getElementById('legend');
[
null,
['#f87171',null,'球体威胁 — 全向预警雷达'],
['#fb923c',null,'锥体威胁 — 定向雷达波束 (地面截断)'],
['#38bdf8',null,'圆柱威胁 — 天气/区域威胁'],
['#2dd4bf',null,'椭圆柱威胁 — CAP 巡逻走廊'],
['#a855f7',null,'禁飞区 — 限制空域'],
null,
['#ff5f7c',null,'目标 / 进入区 — 红色标记与到达球'],
['#10b981',null,'航线(安全) — 无威胁/极低威胁'],
['#facc15',null,'航线(低威胁) — 轻度威胁暴露'],
['#ef4444',null,'航线(高威胁) — 严重威胁穿透'],
['#dc2626',null,'航线(极高威胁) — 致命威胁穿行'],
].forEach(function(a){
if(!a){var sep=document.createElement('div');sep.style.height='3px';leg.appendChild(sep);return;}
var item=document.createElement('div');item.className='legendItem';
item.innerHTML='<span class="legendSwatch" style="background:'+a[0]+'"></span><div class="legendText"><strong>'+a[2]+'</strong></div>';
leg.appendChild(item);
});

// ============================================================
// 威胁渲染
// ============================================================

// --- 球体 ---
DATA.threats.spheres.forEach(function(s){
var ent=viewer.entities.add({
position:dPt(s.center[0],s.center[1],s.center[2]),
ellipsoid:{radii:new Cesium.Cartesian3(s.radius_m,s.radius_m,s.radius_m),
material:hexC('#f87171',0.06+s.threat_level*0.08),outline:true,outlineColor:hexC('#f87171',0.45)},
description:'<b>'+s.id+'</b><br/>球体威胁<br/>半径: '+(s.radius_m/1000).toFixed(1)+' km<br/>威胁等级: '+s.threat_level.toFixed(2),
});
rL('threats',ent);
tById.set(s.id,{kind:'sphere',items:[ent]});
});

// --- 圆柱体 ---
DATA.threats.cylinders.forEach(function(cy){
var ent=viewer.entities.add({
position:dPt(cy.center[0],cy.center[1],cy.center[2]),
cylinder:{length:cy.height_m,topRadius:cy.radius_m,bottomRadius:cy.radius_m,
material:hexC('#38bdf8',0.05+cy.threat_level*0.06),outline:true,outlineColor:hexC('#38bdf8',0.35)},
description:'<b>'+cy.id+'</b><br/>圆柱威胁<br/>半径: '+(cy.radius_m/1000).toFixed(1)+' km<br/>高度: '+(cy.height_m/1000).toFixed(1)+' km',
});
rL('threats',ent);
tById.set(cy.id,{kind:'cyl',items:[ent]});
});

// --- 椭圆柱体 ---
DATA.threats.elliptic_cylinders.forEach(function(ec){
var avgRadius=(ec.semi_major_m+ec.semi_minor_m)/2;
var ent=viewer.entities.add({
position:dPt(ec.center[0],ec.center[1],ec.center[2]),
cylinder:{length:ec.height_m,topRadius:avgRadius,bottomRadius:avgRadius,
material:hexC('#2dd4bf',0.05+ec.threat_level*0.06),outline:true,outlineColor:hexC('#2dd4bf',0.35)},
description:'<b>'+ec.id+'</b><br/>椭圆柱威脅<br/>半长轴: '+(ec.semi_major_m/1000).toFixed(1)+' km<br/>半短轴: '+(ec.semi_minor_m/1000).toFixed(1)+' km<br/>方位: '+ec.azimuth_deg.toFixed(0)+'°<br/>高度: '+(ec.height_m/1000).toFixed(1)+' km',
});
rL('threats',ent);
var foot=viewer.entities.add({
position:dPt(ec.center[0],ec.center[1],0),
ellipse:{semiMajorAxis:ec.semi_major_m,semiMinorAxis:ec.semi_minor_m,
rotation:Cesium.Math.toRadians(90-ec.azimuth_deg),
material:hexC('#2dd4bf',0.06),outline:true,outlineColor:hexC('#2dd4bf',0.4),outlineWidth:2,height:0},
});
rL('threats',foot);
tById.set(ec.id,{kind:'ellip',items:[ent,foot]});
});

// --- 禁飞区 ---
DATA.threats.no_fly_zones.forEach(function(nfz){
var ent=viewer.entities.add({
position:dPt(nfz.center[0],nfz.center[1],nfz.center[2]),
cylinder:{length:nfz.height_m,topRadius:nfz.radius_m,bottomRadius:nfz.radius_m,
material:hexC('#a855f7',0.12),outline:true,outlineColor:hexC('#c084fc',0.5)},
description:'<b>'+nfz.id+'</b><br/>禁飞区<br/>半径: '+(nfz.radius_m/1000).toFixed(1)+' km<br/>高度: '+(nfz.height_m/1000).toFixed(1)+' km',
});
rL('threats',ent);
tById.set(nfz.id,{kind:'nfz',items:[ent]});
});

// --- 锥体 (地面裁剪) ---
DATA.threats.cones.forEach(function(cone){
var apex=dPt(cone.apex[0],cone.apex[1],cone.apex[2]);
var ef=Cesium.Transforms.eastNorthUpToFixedFrame(apex);
var dir=new Cesium.Cartesian3(cone.direction_enu[0],cone.direction_enu[1],cone.direction_enu[2]);
Cesium.Cartesian3.normalize(dir,dir);
var L=cone.visible_length_m,br=cone.bottom_radius_m;
if(L<10||br<10)return;

var mid=Cesium.Cartesian3.multiplyByScalar(dir,L/2,new Cesium.Cartesian3());
var cross=Cesium.Cartesian3.cross(Cesium.Cartesian3.UNIT_Z,dir,new Cesium.Cartesian3());
var rot=Cesium.Matrix3.clone(Cesium.Matrix3.IDENTITY);
if(Cesium.Cartesian3.magnitude(cross)>1e-8){
Cesium.Cartesian3.normalize(cross,cross);
var ang=Math.acos(Cesium.Math.clamp(Cesium.Cartesian3.dot(Cesium.Cartesian3.UNIT_Z,dir),-1,1));
rot=Cesium.Matrix3.fromQuaternion(Cesium.Quaternion.fromAxisAngle(cross,ang));
}else if(dir.z<0){rot=Cesium.Matrix3.fromRotationX(Cesium.Math.PI);}

var lf=Cesium.Matrix4.fromRotationTranslation(rot,mid);
var mm=Cesium.Matrix4.multiply(ef,lf,new Cesium.Matrix4());
var geo=new Cesium.CylinderGeometry({length:L,topRadius:br,bottomRadius:0,slices:64});
var prim=viewer.scene.primitives.add(new Cesium.Primitive({
geometryInstances:new Cesium.GeometryInstance({geometry:geo,
attributes:{color:Cesium.ColorGeometryInstanceAttribute.fromColor(hexC('#fb923c',0.1+cone.threat_level*0.12))}}),
appearance:new Cesium.PerInstanceColorAppearance({translucent:true,closed:false}),
modelMatrix:mm}));
rL('threats',prim);
tById.set(cone.id,{kind:'cone',items:[prim]});
});

// ============================================================
// 平台标记
// ============================================================
DATA.platforms.forEach(function(p,i){
var c=hexC(PLATFORM_COLORS[i%PLATFORM_COLORS.length],1);
var ent=viewer.entities.add({
position:dPt(p.position[0],p.position[1],p.position[2]),
point:{pixelSize:10,color:c,outlineColor:Cesium.Color.BLACK,outlineWidth:2,disableDepthTestDistance:Number.POSITIVE_INFINITY},
label:{text:p.id,font:'600 12px sans-serif',fillColor:c,outlineColor:Cesium.Color.BLACK,outlineWidth:3,
style:Cesium.LabelStyle.FILL_AND_OUTLINE,pixelOffset:new Cesium.Cartesian2(0,-20),disableDepthTestDistance:Number.POSITIVE_INFINITY},
});
rL('targets',ent);
});

// ============================================================
// 目标标记
// ============================================================
DATA.targets.forEach(function(t){
var ent=viewer.entities.add({
position:dPt(t.position[0],t.position[1],t.position[2]),
point:{pixelSize:12,color:hexC('#ff5f7c',1),outlineColor:Cesium.Color.BLACK,outlineWidth:2,disableDepthTestDistance:Number.POSITIVE_INFINITY},
label:{text:t.id,font:'700 13px sans-serif',fillColor:hexC('#ff5f7c',1),outlineColor:Cesium.Color.BLACK,outlineWidth:3,
style:Cesium.LabelStyle.FILL_AND_OUTLINE,pixelOffset:new Cesium.Cartesian2(0,-22),disableDepthTestDistance:Number.POSITIVE_INFINITY},
});
rL('targets',ent);
var ae=viewer.entities.add({
position:dPt(t.position[0],t.position[1],t.position[2]),
ellipsoid:{radii:new Cesium.Cartesian3(t.arrival_radius_km*1000,t.arrival_radius_km*1000,t.arrival_radius_km*1000),
material:hexC('#ff5f7c',0.04),outline:true,outlineColor:hexC('#ff5f7c',0.25)},
});
rL('targets',ae);
});

// ============================================================
// 显式 waypoint 标记
// ============================================================
DATA.waypoints.forEach(function(wp){
var ent=viewer.entities.add({
position:dPt(wp.position[0],wp.position[1],wp.position[2]),
point:{pixelSize:11,color:hexC('#22d3ee',0.95),outlineColor:Cesium.Color.BLACK,outlineWidth:2,disableDepthTestDistance:Number.POSITIVE_INFINITY},
label:{text:'WP '+wp.id,font:'600 11px sans-serif',fillColor:hexC('#22d3ee',1),outlineColor:Cesium.Color.BLACK,outlineWidth:3,
style:Cesium.LabelStyle.FILL_AND_OUTLINE,pixelOffset:new Cesium.Cartesian2(0,-20),disableDepthTestDistance:Number.POSITIVE_INFINITY},
});
rL('targets',ent);
});

// ============================================================
// 航线 (威胁分段着色)
// ============================================================
function tColor(v){
if(v<=0.0001)return'#10b981';if(v<=0.01)return'#34d399';
if(v<=0.05)return'#a3e635';if(v<=0.1)return'#facc15';
if(v<=0.3)return'#f97316';if(v<=0.5)return'#ef4444';
return'#dc2626';
}

DATA.paths.forEach(function(path){
var wps=path.waypoints,thr=path.wp_threat_costs;
var rid=path.routeId,bc=path.color,isMain=path.rank===0;

var re={path:path,segEnts:[],glowEnt:null,shEnt:null,markers:[]};
routeMap.set(rid,re);
var segs=[],segS=0,segC=tColor(thr[0]||0);
for(var i=1;i<wps.length;i++){
var tc=tColor(thr[i]||0);
if(tc!==segC){segs.push({s:segS,e:i,c:segC});segS=i;segC=tc;}
}
segs.push({s:segS,e:wps.length-1,c:segC});

var segEnts=[];
segs.forEach(function(seg){
var poly=buildCurved(wps.slice(seg.s,seg.e+1));
var ent=viewer.entities.add({polyline:{
positions:Cesium.Cartesian3.fromDegreesArrayHeights(poly),
width:isMain?5:3,material:hexC(seg.c,isMain?0.95:0.65),
arcType:Cesium.ArcType.GEODESIC,granularity:Cesium.Math.RADIANS_PER_DEGREE,clampToGround:false,
disableDepthTestDistance:Number.POSITIVE_INFINITY},
});
rL('paths',ent);segEnts.push(ent);re.segEnts.push(ent);
});

var flat=buildCurved(wps);
var glow=viewer.entities.add({polyline:{
positions:Cesium.Cartesian3.fromDegreesArrayHeights(flat),
width:isMain?14:7,
material:new Cesium.PolylineGlowMaterialProperty({glowPower:isMain?0.25:0.12,taperPower:0.7,color:hexC(bc,isMain?0.35:0.15)}),
arcType:Cesium.ArcType.GEODESIC,granularity:Cesium.Math.RADIANS_PER_DEGREE,clampToGround:false,
disableDepthTestDistance:Number.POSITIVE_INFINITY},
});
rL('pathGlow',glow);re.glowEnt=glow;

var shadow=buildCurved(wps.map(function(w){return[w[0],w[1],0];}));
var shEnt=viewer.entities.add({polyline:{
positions:Cesium.Cartesian3.fromDegreesArrayHeights(shadow),
width:isMain?2:1.2,material:hexC(bc,isMain?0.15:0.06),
arcType:Cesium.ArcType.GEODESIC,granularity:Cesium.Math.RADIANS_PER_DEGREE,clampToGround:false,
disableDepthTestDistance:Number.POSITIVE_INFINITY},
});
rL('shadows',shEnt);re.shEnt=shEnt;

if(path.control_point){
var cpColor=path.control_point_kind==='attack_point'?hexC('#f59e0b',0.95):hexC('#a78bfa',0.95);
var aEnt=viewer.entities.add({
position:dPt(path.control_point[0],path.control_point[1],path.control_point[2]),
point:{pixelSize:10,color:cpColor,outlineColor:Cesium.Color.WHITE.withAlpha(0.95),outlineWidth:2,disableDepthTestDistance:Number.POSITIVE_INFINITY},
label:{text:path.control_point_label||path.control_point_kind||'control_point',font:'600 10px sans-serif',fillColor:cpColor,outlineColor:Cesium.Color.BLACK,outlineWidth:3,
style:Cesium.LabelStyle.FILL_AND_OUTLINE,pixelOffset:new Cesium.Cartesian2(0,-16),disableDepthTestDistance:Number.POSITIVE_INFINITY},
});
rL('targets',aEnt);aEnt._isRoute=true;re.markers.push(aEnt);
}

wps.forEach(function(w,i){
if(i===0||i===wps.length-1){
var pEnt=viewer.entities.add({
position:dPt(w[0],w[1],w[2]),
point:{pixelSize:i===0?8:9,color:hexC(bc,1),outlineColor:Cesium.Color.WHITE.withAlpha(0.9),outlineWidth:2,disableDepthTestDistance:Number.POSITIVE_INFINITY},
});
rL('targets',pEnt);pEnt._isRoute=true;re.markers.push(pEnt);
}
});
});

// ============================================================
// 加油段渲染 (start/end markers + connecting polyline)
// ============================================================
var rsData=DATA.refuel_segments||[];
rsData.forEach(function(rs){
var sPos=rs.start_position,ePos=rs.end_position;
var adjusted=rs.adjusted;
var c=adjusted?Cesium.Color.fromCssColorString('#f97316'):Cesium.Color.fromCssColorString('#22c55e');
var distStr=rs.refuel_distance_km?(' '+rs.refuel_distance_km.toFixed(1)+'km'):'';
var labelText=rs.platform_id+'加油'+(adjusted?'(回退)':'')+distStr;
// 开始点 (菱形标记)
viewer.entities.add({
position:dPt(sPos[0],sPos[1],sPos[2]||0),
point:{pixelSize:8,color:c,outlineColor:Cesium.Color.WHITE.withAlpha(0.9),outlineWidth:1,disableDepthTestDistance:Number.POSITIVE_INFINITY},
label:{text:labelText,font:'600 9px sans-serif',fillColor:c,outlineColor:Cesium.Color.BLACK,outlineWidth:3,
style:Cesium.LabelStyle.FILL_AND_OUTLINE,pixelOffset:new Cesium.Cartesian2(0,-14),disableDepthTestDistance:Number.POSITIVE_INFINITY},
});
// 结束点 (方形标记)
viewer.entities.add({
position:dPt(ePos[0],ePos[1],ePos[2]||0),
point:{pixelSize:9,color:c,outlineColor:Cesium.Color.WHITE.withAlpha(0.9),outlineWidth:1,disableDepthTestDistance:Number.POSITIVE_INFINITY},
});
// 连接线 (虚线)
var poly=buildCurved([sPos,ePos]);
viewer.entities.add({
polyline:{positions:Cesium.Cartesian3.fromDegreesArrayHeights(poly),
width:3,material:new Cesium.PolylineDashMaterialProperty({color:c,dashLength:8}),
arcType:Cesium.ArcType.GEODESIC,granularity:Cesium.Math.RADIANS_PER_DEGREE,clampToGround:false,
disableDepthTestDistance:Number.POSITIVE_INFINITY},
});
});

// ============================================================
// 威胁开关面板
// ============================================================
var ttEl=document.getElementById('threatToggles');
tById.forEach(function(rec,name){
if(!rec.kind)return;
var row=document.createElement('div');row.className='threatItem';
var kind=rec.kind;
var badgeMap={sphere:'球体',cone:'锥体',cyl:'圆柱',ellip:'椭圆柱',nfz:'禁飞'};
var badgeCls='badge badge-'+({sphere:'sphere',cone:'cone',cyl:'cyl',ellip:'ellip',nfz:'nfz'}[kind]||'cyl');
row.innerHTML='<label><input type="checkbox" checked/><span>'+name+'</span></label><span class="'+badgeCls+'">'+(badgeMap[kind]||kind)+'</span>';
row.querySelector('input').addEventListener('change',function(e){
rec.items.forEach(function(it){if(it&&typeof it.show!=='undefined')it.show=e.target.checked;});
});
ttEl.appendChild(row);
});

// ============================================================
// 航线清单
// ============================================================
var rl=document.getElementById('routeList');
DATA.paths.forEach(function(path){
var card=document.createElement('div');card.className='routeCard';
var hasStealth=path.direction_label.indexOf('_stealth')>=0;
var cpKind=path.control_point_kind||'';
var modeLabel=hasStealth?'隐身':(cpKind==='attack_point'?'发射':(cpKind==='approach_ref'?'入射':'直达'));
var modeCls='mode-'+(hasStealth?'launch':(cpKind==='attack_point'?'launch':(cpKind==='approach_ref'?'anchor':'direct')));
var segHTML=path.segment_colors.map(function(c){return'<span class="rseg" style="background:'+c+'"></span>';}).join('');
card.innerHTML='<div class="rhead"><span class="rdot" style="background:'+path.color+'"></span><span class="rname">'+path.platform_id+' → '+path.target_id+'</span><span class="rmode '+modeCls+'">'+modeLabel+'</span></div><div class="rinfo"><span>方向 '+path.direction[0]+'°/'+path.direction[1]+'°</span><span>'+path.waypoints.length+' 航点</span><span>代价 '+Math.round(path.cost)+'</span><span>威胁 '+path.threat_exposure.toFixed(2)+'</span></div><div class="rbar">'+segHTML+'</div>';
card.addEventListener('click',function(){selRoute(path.routeId,card);});
rl.appendChild(card);
});

function selRoute(rid,cardEl){
if(isoRid===rid){
isoRid=null;
document.querySelectorAll('.routeCard.sel').forEach(function(c){c.classList.remove('sel');});
applyVisibility();
ppEl.classList.remove('show');
updatePanelHeader();
return;
}
isoRid=rid;
document.querySelectorAll('.routeCard.sel').forEach(function(c){c.classList.remove('sel');});
if(cardEl)cardEl.classList.add('sel');
applyVisibility();
showProfile(rid);
updatePanelHeader();
var e=routeMap.get(rid);if(!e)return;
var wps=e.path.waypoints;
var poss=wps.map(function(w){return dPt(w[0],w[1],w[2]);});
var b=Cesium.BoundingSphere.fromPoints(poss);
viewer.camera.flyToBoundingSphere(b,{duration:0.8,
offset:new Cesium.HeadingPitchRange(Cesium.Math.toRadians(45),Cesium.Math.toRadians(-25),b.radius*1.6)});
}

function updatePanelHeader(){
var total=routeMap.size;
document.getElementById('routePanelTitle').textContent=isoRid?'航线清单 (1/'+total+')':'航线清单';
document.getElementById('routePanelSub').textContent=isoRid?'已聚焦单条航线 — 再次点击同一航线可返回全部视图':'点击航线查看详情与高度剖面';
document.getElementById('showAllBtn').style.display=isoRid?'block':'none';
}
document.getElementById('showAllBtn').addEventListener('click',function(){
var cards=document.querySelectorAll('.routeCard.sel');
if(cards.length>0)selRoute(isoRid,cards[0]);
});

// ============================================================
// 高度剖面图
// ============================================================
var ppEl=document.getElementById('profilePanel');
document.getElementById('profileClose').addEventListener('click',function(){ppEl.classList.remove('show');});

function showProfile(rid){
var e=routeMap.get(rid);if(!e)return;
var profile=e.path.alt_profile;
if(!profile||profile.length<2)return;
ppEl.classList.add('show');
var lbl=e.path.direction_label;
var hasLaunch=lbl.indexOf('_launch')>=0;
var hasStealth=lbl.indexOf('_stealth')>=0;
document.getElementById('profileTitle').textContent='高度剖面 — '+e.path.platform_id+' → '+(hasLaunch?(hasStealth?'发射点(隐身)':'发射点'):e.path.target_id);

var cvs=document.getElementById('profileCanvas');
var rect=cvs.parentElement.getBoundingClientRect();
var dpr=window.devicePixelRatio||1;
cvs.width=rect.width*dpr;cvs.height=(rect.height-28)*dpr;
cvs.style.width=rect.width+'px';cvs.style.height=(rect.height-28)+'px';
var ctx=cvs.getContext('2d');
ctx.scale(dpr,dpr);
var W=rect.width-4,H=rect.height-32;
ctx.clearRect(0,0,W,H);
var m={t:8,r:24,b:22,l:42};
var pw=W-m.l-m.r,ph=H-m.t-m.b;

var dMin=profile[0][0],dMax=profile[profile.length-1][0];
var aMin=0,aMax=Math.max(1,profile.reduce(function(mx,p){return Math.max(mx,p[1]);},0))*1.15;
var tMax=Math.max(0.001,profile.reduce(function(mx,p){return Math.max(mx,p[2]);},0));

function x(d){return m.l+(d-dMin)/(dMax-dMin||1)*pw;}
function y(a){return m.t+ph-a/aMax*ph;}

for(var i=0;i<profile.length-1;i++){
var x0=x(profile[i][0]),x1=x(profile[i+1][0]);
var midT=((profile[i][2]+profile[i+1][2])/2)/tMax;
var rr=Math.round(Math.min(1,midT*2.5)*200+40);
var gg=Math.round((1-Math.min(1,midT*2))*160+30);
var bb=Math.round((1-Math.min(1,midT*1.5))*160+30);
ctx.fillStyle='rgba('+rr+','+gg+','+bb+',0.12)';
ctx.fillRect(x0,m.t,x1-x0,ph);
}

ctx.strokeStyle='rgba(255,255,255,0.05)';ctx.lineWidth=0.5;
for(var ak=0;ak<=aMax;ak+=Math.max(1,Math.round(aMax/5))){
var ya=y(ak);ctx.beginPath();ctx.moveTo(m.l,ya);ctx.lineTo(W-m.r,ya);ctx.stroke();
ctx.fillStyle='rgba(255,255,255,0.4)';ctx.font='8px sans-serif';ctx.textAlign='right';
ctx.fillText(ak+'m',m.l-4,ya+3);
}
for(var dk=dMin;dk<=dMax;dk+=Math.max(1,Math.round((dMax-dMin)/4))){
var xd=x(dk);ctx.beginPath();ctx.moveTo(xd,m.t);ctx.lineTo(xd,m.t+ph);ctx.stroke();
ctx.textAlign='center';ctx.fillText(dk.toFixed(0)+'km',xd,m.t+ph+13);
}

ctx.beginPath();ctx.moveTo(x(profile[0][0]),y(profile[0][1]));
for(var j=1;j<profile.length;j++)ctx.lineTo(x(profile[j][0]),y(profile[j][1]));
ctx.lineTo(x(profile[profile.length-1][0]),m.t+ph);
ctx.lineTo(x(profile[0][0]),m.t+ph);ctx.closePath();
ctx.fillStyle='rgba(96,165,250,0.08)';ctx.fill();

ctx.beginPath();ctx.strokeStyle='rgba(96,165,250,0.8)';ctx.lineWidth=2;
ctx.moveTo(x(profile[0][0]),y(profile[0][1]));
for(var k=1;k<profile.length;k++)ctx.lineTo(x(profile[k][0]),y(profile[k][1]));
ctx.stroke();

profile.forEach(function(p,idx){
var px=x(p[0]),py=y(p[1]);
var tc=p[2];
var fc=tc>0.1?'#ef4444':tc>0.01?'#f97316':tc>0.001?'#facc15':'#34d399';
ctx.beginPath();ctx.arc(px,py,idx===0||idx===profile.length-1?4:2.5,0,Math.PI*2);
ctx.fillStyle=fc;ctx.fill();
ctx.strokeStyle='rgba(255,255,255,0.6)';ctx.lineWidth=1;ctx.stroke();
});

ctx.fillStyle='rgba(255,255,255,0.4)';ctx.textAlign='center';ctx.font='bold 8px sans-serif';
ctx.fillText('距离 (km)',W/2,H-2);
ctx.save();ctx.translate(8,m.t+ph/2);ctx.rotate(-Math.PI/2);ctx.fillText('高度 (m)',0,0);ctx.restore();
}

// ============================================================
// 初始化
// ============================================================
setTimeout(function(){
var b=cBounds();if(b){
viewer.camera.flyToBoundingSphere(b,{duration:0.5,
offset:new Cesium.HeadingPitchRange(Cesium.Math.toRadians(20),Cesium.Math.toRadians(-45),b.radius*2.2)});
}
if(DATA.paths.length>0){
var cards=document.querySelectorAll('.routeCard');
if(cards.length>0)selRoute(DATA.paths[0].routeId,cards[0]);
}
applyVisibility();updatePanelHeader();
},400);

})();
</script>
</body>
</html>"""
