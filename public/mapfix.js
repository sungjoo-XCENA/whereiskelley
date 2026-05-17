(function () {
  const geocodeCache = new Map();

  function hasCoordinates(group) {
    return Number.isFinite(Number(group.lat)) && Number.isFinite(Number(group.lng));
  }

  function geocodeAddressForGroup(group) {
    const venue = group.venue || {};
    const parts = [
      displayVenueName(venue),
      venue.address && venue.address !== `${venue.city}, ${venue.country}` ? venue.address : "",
      venue.city,
      venue.country
    ].filter(Boolean);
    return [...new Set(parts)].join(", ");
  }

  function geocodeGroup(group, maps) {
    if (hasCoordinates(group)) return Promise.resolve(group);
    const address = geocodeAddressForGroup(group);
    if (!address || !maps?.Geocoder) return Promise.resolve(group);
    const cacheKey = group.key || address;
    if (geocodeCache.has(cacheKey)) {
      const cached = geocodeCache.get(cacheKey);
      return Promise.resolve(cached ? { ...group, ...cached } : group);
    }
    const geocoder = new maps.Geocoder();
    return new Promise((resolve) => {
      geocoder.geocode({ address }, (results, status) => {
        if (status !== "OK" || !results?.[0]?.geometry?.location) {
          geocodeCache.set(cacheKey, null);
          resolve(group);
          return;
        }
        const location = results[0].geometry.location;
        const coordinates = {
          lat: location.lat(),
          lng: location.lng(),
          geocoded: true,
          geocodedAddress: results[0].formatted_address || address
        };
        geocodeCache.set(cacheKey, coordinates);
        resolve({ ...group, ...coordinates });
      });
    });
  }

  renderMap = function renderMap(results) {
    const groups = groupedVenues(results);
    latestMapVenues = groups.filter(hasCoordinates);
    mapSummaryEl.textContent = groups.length
      ? "Locating matching places..."
      : "No matching places to map";
    drawGoogleMap(groups);
  };

  drawGoogleMap = async function drawGoogleMap(groups) {
    const token = ++mapRenderToken;
    if (!groups.length) {
      clearGoogleMarkers();
      showMapFallback("No matching places were found for this search.", "No mapped places");
      return;
    }
    try {
      const maps = await loadGoogleMaps();
      if (token !== mapRenderToken) return;
      if (!maps) {
        showMapFallback("The map is hidden because the deployed Google Maps key is not configured.", "Map unavailable");
        return;
      }
      mapSummaryEl.textContent = "Locating places with Google Maps...";
      const located = [];
      for (const group of groups) {
        if (token !== mapRenderToken) return;
        located.push(await geocodeGroup(group, maps));
      }
      const mappedVenues = located.filter(hasCoordinates);
      latestMapVenues = mappedVenues;
      const totalLines = mappedVenues.reduce((sum, group) => sum + group.results.length, 0);
      const geocodedCount = mappedVenues.filter((group) => group.geocoded).length;
      mapSummaryEl.textContent = mappedVenues.length
        ? `${mappedVenues.length} places on map / ${totalLines} matching wines${geocodedCount ? `, ${geocodedCount} found by Google` : ""}`
        : "No mapped places yet";
      if (!mappedVenues.length) {
        clearGoogleMarkers();
        showMapFallback("Google Maps could not locate these places from the available name, city, and country.", "No mapped places");
        return;
      }
      mapFallbackEl.classList.add("hidden");
      googleMapEl.classList.remove("hidden");
      if (!googleMap) {
        googleMap = new maps.Map(googleMapEl, {
          center: { lat: 25, lng: 8 },
          zoom: 2,
          mapTypeControl: false,
          streetViewControl: false,
          fullscreenControl: true,
          clickableIcons: false,
          styles: [
            { featureType: "poi", stylers: [{ visibility: "off" }] },
            { featureType: "transit", stylers: [{ visibility: "off" }] }
          ]
        });
        googleInfoWindow = new maps.InfoWindow();
      }
      clearGoogleMarkers();
      const bounds = new maps.LatLngBounds();
      for (const group of mappedVenues) {
        const position = { lat: Number(group.lat), lng: Number(group.lng) };
        bounds.extend(position);
        const marker = new maps.Marker({
          map: googleMap,
          position,
          title: displayVenueName(group.venue) || "Wine venue",
        });
        marker.starWineKey = group.key;
        marker.addListener("click", () => selectVenueGroup(group));
        googleMarkers.push(marker);
      }
      googleMap.fitBounds(bounds, 56);
      if (mappedVenues.length === 1) {
        googleMap.setZoom(15);
      }
      setActiveMapMarker(activeVenueKey);
    } catch (error) {
      showMapFallback(error.message, "Map unavailable");
    }
  };
})();
