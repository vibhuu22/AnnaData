"""
Soil properties from OpenLandMap via Google Earth Engine.

Earth Engine is optional; if it is not configured the tool returns a short
"unavailable" string that the prompt can safely include.
"""
import startup

TEXTURE_MAP = {
    1: "Sand", 2: "Loamy sand", 3: "Sandy loam", 4: "Loam", 5: "Silt loam",
    6: "Silt", 7: "Sandy clay loam", 8: "Clay loam", 9: "Silty clay loam",
    10: "Sandy clay", 11: "Silty clay", 12: "Clay",
}


def soil_tool(lat: float, lon: float) -> str:
    """Return a soil report for a coordinate, or an unavailable notice."""
    if not startup.init_earth_engine():
        return "Soil data unavailable (Earth Engine not configured)."

    try:
        import ee

        point = ee.Geometry.Point(lon, lat)

        texture_img = ee.Image("OpenLandMap/SOL/SOL_TEXTURE-CLASS_USDA-TT_M/v02")
        texture_val = texture_img.sample(point, 250).first().get("b0").getInfo()
        texture = TEXTURE_MAP.get(texture_val, f"Unknown ({texture_val})")

        ph_img = ee.Image("OpenLandMap/SOL/SOL_PH-H2O_USDA-4C1A2A_M/v02")
        ph_val = ph_img.sample(point, 250).first().get("b0").getInfo() / 10

        soc_img = ee.Image("OpenLandMap/SOL/SOL_ORGANIC-CARBON_USDA-6A1C_M/v02")
        soc_val = soc_img.sample(point, 250).first().get("b0").getInfo()

        return (
            f"Soil Report for ({lat}, {lon}):\n"
            f"- Soil texture (USDA class): {texture}\n"
            f"- Soil pH: {ph_val:.2f}\n"
            f"- Soil organic carbon: {soc_val:.2f}%\n"
        )

    except Exception as e:
        print(f"Soil lookup failed for ({lat}, {lon}): {e}")
        return "Soil data unavailable (lookup failed)."
