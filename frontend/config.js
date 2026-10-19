// Website settings. This is the only file to edit when deploying.
window.SERUEN_CONFIG = {
  // Address of Tomiris's backend, e.g. "https://seruen-api.onrender.com" (no slash at the end).
  // Set it with: python scripts/set_api_url.py https://...   ("" = same address as this site).
  API_URL: "https://seruen-backend-f36d.onrender.com",

  // Available interface features; optional backend features also check /health.
  FEATURES: {
    mapLinks: true,   // "Route in 2GIS / Google Maps" buttons on each card
    weather: true,    // Astana weather from Open-Meteo -> context.weather
    route: true,      // Start a server-planned walk to the selected place, including confirmed stops
    languages: true,  // KZ / RU / EN switch
    twogis: true,     // "2GIS rating & hours" button on each card: asks the backend only when pressed
    photos: true,     // photos of each place + what Gemini sees on them (lighting, seats, kids' area, space)
  },

  // Route line geometry. The public OSRM demo server; if it fails we draw straight lines.
  OSRM_URL: "https://routing.openstreetmap.de/routed-foot",
};
