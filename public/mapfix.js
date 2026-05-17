(function () {
  const geocodeCache = new Map();

  function coordinateValue(value) {
    if (value === null || value === undefined || value === "") return null;
    const number = Number(value);
    return Number.isFinite(number) ? number : null;
  }

  function hasCoordinates(group) {
    return coordinateValue(group.lat) !== null && coordinateValue(group.lng) !== null;
  }

  function asciiFold(value) {
    return String(value || "")
      .normalize("NFKD")
      .replace(/[\u0300-\u036f]/g, "")
      .replace(/[øØ]/g, (char) => char === "Ø" ? "O" : "o")
      .replace(/[æÆ]/g, (char) => char === "Æ" ? "AE" : "ae")
      .replace(/[åÅ]/g, (char) => char === "Å" ? "A" : "a");
  }

  groupedVenues = function groupedVenues(results) {
    const groups = new Map();
    for (const result of results) {
      const venue = result.venue || {};
      const key = venueKey(result);
      if (!key) continue;
      if (!groups.has(key)) {
        groups.set(key, {
          key,
          venue,
          results: [],
          lat: coordinateValue(venue.lat),
          lng: coordinateValue(venue.lng)
        });
      }
      groups.get(key).results.push(result);
    }
    for (const group of groups.values()) {
      group.results = uniqueResults(group.results);
    }
    return [...groups.values()].sort((a, b) => String(a.venue?.name || "").localeCompare(String(b.venue?.name || "")));
  };

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

  function geocodeQueriesForGroup(group) {
    const venue = group.venue || {};
    const name = displayVenueName(venue);
    const city = venue.city || "";
    const country = venue.country || "";
    const address = venue.address && venue.address !== `${city}, ${country}` ? venue.address : "";
    const placeQueries = [
      { address: [name, address, city, country].filter(Boolean).join(", "), approximate: false },
      { address: [name, "restaurant", city, country].filter(Boolean).join(", "), approximate: false },
      { address: [name, city, country].filter(Boolean).join(", "), approximate: false },
      { address: [asciiFold(name), "restaurant", asciiFold(city), country].filter(Boolean).join(", "), approximate: false },
      { address: [asciiFold(name), asciiFold(city), country].filter(Boolean).join(", "), approximate: false }
    ];
    const cityQueries = [
      { address: [city, country].filter(Boolean).join(", "), approximate: true },
      { address: [asciiFold(city), country].filter(Boolean).join(", "), approximate: true }
    ];
    const seen = new Set();
    return [...placeQueries, ...cityQueries].filter((query) => {
      if (!query.address || seen.has(query.address)) return false;
      seen.add(query.address);
      return true;
    });
  }

  function countryRestriction(country) {
    const value = String(country || "").toLowerCase();
    const map = {
      australia: "AU",
      austria: "AT",
      belgium: "BE",
      denmark: "DK",
      france: "FR",
      germany: "DE",
      "greater china": "CN",
      "hong kong": "HK",
      italy: "IT",
      netherlands: "NL",
      norway: "NO",
      singapore: "SG",
      spain: "ES",
      sweden: "SE",
      uk: "GB",
      usa: "US"
    };
    return map[value] || "";
  }

  function geocodeOnce(geocoder, request) {
    return new Promise((resolve) => {
      geocoder.geocode(request, (results, status) => resolve({ results, status }));
    });
  }

  async function geocodeGroup(group, maps) {
    if (hasCoordinates(group)) return Promise.resolve(group);
    const queries = geocodeQueriesForGroup(group);
    if (!queries.length || !maps?.Geocoder) return Promise.resolve(group);
    const cacheKey = group.key || queries[0].address;
    if (geocodeCache.has(cacheKey)) {
      const cached = geocodeCache.get(cacheKey);
      return Promise.resolve(cached ? { ...group, ...cached } : group);
    }
    const geocoder = new maps.Geocoder();
    const restriction = countryRestriction(group.venue?.country);
    const statuses = [];
    for (const query of queries) {
      const address = query.address;
      const request = restriction
        ? { address, componentRestrictions: { country: restriction } }
        : { address };
      const { results, status } = await geocodeOnce(geocoder, request);
      statuses.push(`${address}: ${status}`);
      if (status === "OK" && results?.[0]?.geometry?.location) {
        const result = results[0];
        const location = result.geometry.location;
        const coordinates = {
          lat: location.lat(),
          lng: location.lng(),
          geocoded: true,
          geocodedAddress: result.formatted_address || address,
          geocodeQuery: address,
          approximate: query.approximate
        };
        geocodeCache.set(cacheKey, coordinates);
        return { ...group, ...coordinates };
      }
      if (status === "REQUEST_DENIED") break;
    }
    geocodeCache.set(cacheKey, null);
    return { ...group, geocodeFailed: true, geocodeStatus: statuses.join(" | ") };
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
      const failedCount = located.filter((group) => group.geocodeFailed).length;
      latestMapVenues = mappedVenues;
      const totalLines = mappedVenues.reduce((sum, group) => sum + group.results.length, 0);
      const geocodedCount = mappedVenues.filter((group) => group.geocoded).length;
      const approximateCount = mappedVenues.filter((group) => group.approximate).length;
      mapSummaryEl.textContent = mappedVenues.length
        ? `${mappedVenues.length} places on map / ${totalLines} matching wines${geocodedCount ? `, ${geocodedCount} found by Google` : ""}${approximateCount ? `, ${approximateCount} city-level` : ""}${failedCount ? `, ${failedCount} not located` : ""}`
        : "No mapped places yet";
      if (!mappedVenues.length) {
        clearGoogleMarkers();
        const failed = located.find((group) => group.geocodeFailed);
        showMapFallback(failed?.geocodeStatus || "Google Maps could not locate these places from the available name, city, and country.", "No mapped places");
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
        const position = { lat: coordinateValue(group.lat), lng: coordinateValue(group.lng) };
        bounds.extend(position);
        const marker = new maps.Marker({
          map: googleMap,
          position,
          title: `${displayVenueName(group.venue) || "Wine venue"}${group.approximate ? " (city-level)" : ""}`,
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
