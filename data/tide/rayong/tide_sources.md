# Rayong Tide Sources

## Identified Stations
The following tide stations are relevant to the Rayong coastal analysis AOI:

1. **Map Ta Phut (Rayong)**
   - **Source:** Hydrographic Department, Royal Thai Navy (HDRTN) / Marine Department
   - **Coordinates:** ~ 12° 39' N, 101° 08' E
   - **Datum:** Lowest Low Water (LLW)
   - **Observation/Prediction:** Tide tables provide hourly predictions. Observed data available via direct request.
   - **Distance from AOI:** Map Ta Phut is located immediately west of the central Rayong coastline, making it highly applicable to the AOI (within 10-30 km depending on the plot).
   - **Access:** Annual tide tables published by HDRTN.

2. **Ko Samet**
   - **Source:** HDRTN
   - **Coordinates:** ~ 12° 34' N, 101° 27' E
   - **Distance from AOI:** Located directly offshore from Rayong, very close to the eastern edge of the AOI.
   - **Access:** Annual tide tables.

## Selected Reference Station
**Ko Samet** or **Map Ta Phut** are the best choices. For general shoreline extraction in the Rayong mainland, Map Ta Phut predictions from HDRTN are the standard defensible source.

Since we are currently prototyping and do not have an active API to the Royal Thai Navy's real-time observed data, we will use a **Global Tide Model (e.g., FES2014 or TPXO9)** for the exact satellite acquisition times, validated against the HDRTN Map Ta Phut predictions.
