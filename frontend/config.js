// Website settings. This is the only file to edit when deploying.
window.SERUEN_CONFIG = {
  // Address of Tomiris's backend, e.g. "https://seruen-api.onrender.com" (no slash at the end).
  // Set it with: python scripts/set_api_url.py https://...   ("" = same address as this site).
  API_URL: "https://seruen-backend-f36d.onrender.com",

  // Level-1 extras. Anything not finished by Monday 13:00 -> set to false.
  FEATURES: {
    mapLinks: true,   // "Route in 2GIS / Google Maps" buttons on each card
    weather: true,    // Astana weather from Open-Meteo -> context.weather
    route: true,      // "Build a route" from 3 places, line on the map (computed in the browser)
    languages: true,  // KZ / RU / EN switch
    pirate: true,     // pirate theme, parrot captain, treasure chests on the map
    points: true,     // coins for visited places, stored only in this browser
  },

  // Route line geometry. The public OSRM demo server; if it fails we draw straight lines.
  OSRM_URL: "https://router.project-osrm.org",
};
