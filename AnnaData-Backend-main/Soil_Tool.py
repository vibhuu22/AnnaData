"""
Soil properties from OpenLandMap via Google Earth Engine.

Values are read at b0 - the surface layer - which is the depth agronomic advice
is concerned with. Both source datasets store scaled integers, and getting the
scaling wrong is not a cosmetic problem: organic carbon reported at twice its
real value turns "low, add compost" into "adequate".

  pH             stored x10   -> divide by 10        (4.2-11.0)
  organic carbon stored /5    -> multiply by 5 = g/kg, and /10 again for %

Earth Engine is optional; if it is not configured the tool returns a short
notice the prompt can safely include.
"""
import startup

TEXTURE_MAP = {
    1: "Sand", 2: "Loamy sand", 3: "Sandy loam", 4: "Loam", 5: "Silt loam",
    6: "Silt", 7: "Sandy clay loam", 8: "Clay loam", 9: "Silty clay loam",
    10: "Sandy clay", 11: "Silty clay", 12: "Clay",
}

# Indian Soil Health Card interpretation bands. The rating drives the advice
# far more than the raw number does.
def _rate_organic_carbon(percent: float) -> str:
    if percent < 0.5:
        return "low"
    if percent <= 0.75:
        return "medium"
    return "high"


def _rate_ph(ph: float) -> str:
    if ph < 5.5:
        return "strongly acidic"
    if ph < 6.5:
        return "slightly acidic"
    if ph <= 7.5:
        return "neutral"
    if ph <= 8.5:
        return "slightly alkaline"
    return "strongly alkaline"


def _sample(image_id: str, point, scale: int = 250):
    """Read band b0 at a point, or None if the sample misses."""
    import ee

    value = ee.Image(image_id).sample(point, scale).first().get("b0").getInfo()
    return None if value is None else float(value)


def soil_tool(lat: float, lon: float) -> str:
    """Return a soil report for a coordinate, or an unavailable notice."""
    if not startup.init_earth_engine():
        return "Soil data unavailable (Earth Engine not configured)."

    try:
        import ee

        point = ee.Geometry.Point(lon, lat)
        lines = [f"Soil Report for ({lat}, {lon}):"]

        # Each property is read independently so one missing layer does not
        # cost the farmer the other two.
        try:
            raw = _sample("OpenLandMap/SOL/SOL_TEXTURE-CLASS_USDA-TT_M/v02", point)
            texture = TEXTURE_MAP.get(int(raw), f"Unknown ({raw})") if raw else "unknown"
            lines.append(f"- Soil texture (USDA class): {texture}")
        except Exception as e:
            print(f"Soil texture unavailable at ({lat}, {lon}): {e}")

        try:
            raw = _sample("OpenLandMap/SOL/SOL_PH-H2O_USDA-4C1A2A_M/v02", point)
            if raw is not None:
                ph = raw / 10.0
                lines.append(f"- Soil pH (H2O): {ph:.1f} ({_rate_ph(ph)})")
        except Exception as e:
            print(f"Soil pH unavailable at ({lat}, {lon}): {e}")

        try:
            raw = _sample("OpenLandMap/SOL/SOL_ORGANIC-CARBON_USDA-6A1C_M/v02", point)
            if raw is not None:
                g_per_kg = raw * 5.0
                percent = g_per_kg / 10.0
                lines.append(
                    f"- Soil organic carbon: {percent:.2f}% "
                    f"({g_per_kg:.1f} g/kg, {_rate_organic_carbon(percent)})"
                )
        except Exception as e:
            print(f"Soil organic carbon unavailable at ({lat}, {lon}): {e}")

        if len(lines) == 1:
            return "Soil data unavailable (no readings at this location)."

        return "\n".join(lines) + "\n"

    except Exception as e:
        print(f"Soil lookup failed for ({lat}, {lon}): {e}")
        return "Soil data unavailable (lookup failed)."
