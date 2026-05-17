(function () {
  const style = document.createElement("style");
  style.textContent = `
    .result-table > thead > tr > th:nth-child(7),
    .result-table > tbody > tr.place-row > td:nth-child(7) {
      display: none !important;
    }
    .map-link,
    .actions.compact a.map-link {
      border-color: rgba(23, 92, 80, 0.28);
      background: #eefaf6;
      color: #0f766e;
    }
    .map-link:hover,
    .actions.compact a.map-link:hover {
      border-color: rgba(23, 92, 80, 0.45);
      background: #dff5ef;
      color: #0f5f58;
    }
  `;
  document.head.appendChild(style);

  function googleMapsSearchUrl(name, place) {
    const query = [name, place].filter(Boolean).join(", ");
    return `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(query)}`;
  }

  function expandedPlaceParts(link) {
    const expanded = link.closest(".expanded-place");
    const name = expanded?.querySelector(".expanded-head b")?.textContent.trim() || "";
    const place = expanded?.querySelector(".expanded-head span")?.textContent.trim() || "";
    return { name, place };
  }

  function tagMapLinks(root = document) {
    root.querySelectorAll(".actions.compact a").forEach((link) => {
      const label = link.textContent.trim().toLowerCase();
      if (label === "map") {
        const { name, place } = expandedPlaceParts(link);
        if (name || place) link.href = googleMapsSearchUrl(name, place);
        link.classList.add("map-link");
      }
      if (label === "star wine list page") {
        link.textContent = "Star Wine";
      }
    });
  }

  const observer = new MutationObserver((mutations) => {
    for (const mutation of mutations) {
      mutation.addedNodes.forEach((node) => {
        if (node.nodeType === Node.ELEMENT_NODE) tagMapLinks(node);
      });
    }
  });
  observer.observe(document.body, { childList: true, subtree: true });
  tagMapLinks();

  function cleanMapVenueName(venue = {}) {
    if (typeof displayVenueName === "function") return displayVenueName(venue);
    return String(venue.name || "Unknown")
      .replace(/^[\s\u00d7\u2715\u2716\u2717\u2718\u274c]+/, "")
      .trim();
  }

  function markerStyleForVenue(venue = {}) {
    const type = String(venue.type || "").toLowerCase();
    const isWineBar = type.includes("wine bar");
    const isRestaurant = type.includes("restaurant");
    if (isWineBar && isRestaurant) {
      return { color: "#7c3aed", label: "B/R" };
    }
    if (isWineBar) {
      return { color: "#0f766e", label: "B" };
    }
    if (isRestaurant) {
      return { color: "#a30f3d", label: "R" };
    }
    return { color: "#4b5563", label: "P" };
  }

  function winePinIcon(maps, venue = {}) {
    const { color, label } = markerStyleForVenue(venue);
    const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="36" height="44" viewBox="0 0 36 44">
      <path fill="${color}" stroke="#ffffff" stroke-width="2.5" d="M18 2.5c-8.1 0-14.7 6.6-14.7 14.7 0 11 14.7 24.3 14.7 24.3s14.7-13.3 14.7-24.3C32.7 9.1 26.1 2.5 18 2.5Z"/>
      <circle cx="18" cy="17.2" r="5.2" fill="#ffffff"/>
      <text x="18" y="20.8" text-anchor="middle" font-family="Arial, sans-serif" font-size="${label.length > 1 ? 7 : 10}" font-weight="800" fill="${color}">${label}</text>
    </svg>`;
    return {
      url: `data:image/svg+xml;charset=UTF-8,${encodeURIComponent(svg)}`,
      scaledSize: new maps.Size(32, 39),
      anchor: new maps.Point(16, 39)
    };
  }

  function refreshMarkerIcons() {
    if (!googleMarkers?.length || typeof google === "undefined" || !google.maps) return;
    for (const marker of googleMarkers) {
      const group = latestMapVenues.find((item) => item.key === marker.starWineKey);
      if (group) {
        marker.setIcon(winePinIcon(google.maps, group.venue));
        marker.setTitle(cleanMapVenueName(group.venue) || "Wine place");
      }
    }
  }

  const previousDrawGoogleMap = drawGoogleMap;
  drawGoogleMap = async function patchedDrawGoogleMap(groups) {
    const result = await previousDrawGoogleMap(groups);
    refreshMarkerIcons();
    return result;
  };

  setActiveMapMarker = function patchedSetActiveMapMarker(key) {
    if (!googleMarkers?.length) return;
    refreshMarkerIcons();
    for (const marker of googleMarkers) {
      const active = marker.starWineKey === key;
      marker.setAnimation(active ? google.maps.Animation.BOUNCE : null);
      window.setTimeout(() => marker.setAnimation(null), 900);
      if (active && googleInfoWindow) {
        const group = latestMapVenues.find((item) => item.key === key);
        if (group) {
          const venueName = cleanMapVenueName(group.venue);
          const place = [group.venue.city, group.venue.country].filter(Boolean).join(", ");
          googleInfoWindow.setContent(`<strong>${escapeHtml(venueName)}</strong><br>${escapeHtml(place)}<br>${group.results.length} matching wines`);
          googleInfoWindow.open({ map: googleMap, anchor: marker });
        }
      }
    }
  };
})();
