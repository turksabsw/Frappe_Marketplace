/**
 * TradeHub Marketplace - Service Worker
 *
 * Strategies:
 *   - Cache-First: Static assets (JS, CSS, images, fonts)
 *   - Network-First: API calls (/api/*, /method/*)
 *   - Stale-While-Revalidate: HTML pages
 *
 * Exclusions: Login, payment, and escrow endpoints are NEVER cached.
 * Fallback: offline.html served when network is unavailable.
 */

const CACHE_VERSION = 'tradehub-v1';
const STATIC_CACHE = `${CACHE_VERSION}-static`;
const API_CACHE = `${CACHE_VERSION}-api`;
const HTML_CACHE = `${CACHE_VERSION}-html`;

const APP_SHELL_ASSETS = [
  '/',
  '/offline.html',
  '/manifest.json'
];

/**
 * URL patterns that must NEVER be cached.
 * Includes login, authentication, payment, and escrow endpoints.
 */
const NEVER_CACHE_PATTERNS = [
  /\/api\/method\/login/,
  /\/api\/method\/logout/,
  /\/api\/method\/frappe\.auth/,
  /\/api\/method\/frappe\.client\.get_csrf_token/,
  /\/api\/method\/frappe\.handler\.upload_file/,
  /\/api\/resource\/Payment/i,
  /\/api\/resource\/Payment%20Intent/i,
  /\/api\/resource\/Payment%20Entry/i,
  /\/api\/resource\/Escrow/i,
  /\/api\/method\/.*payment/i,
  /\/api\/method\/.*escrow/i,
  /\/api\/method\/.*checkout/i,
  /\/api\/method\/.*pay/i,
  /\/login/,
  /\/api\/method\/frappe\.integrations/
];

/**
 * Check whether a request URL should never be cached.
 * @param {string} url
 * @returns {boolean}
 */
function shouldNeverCache(url) {
  return NEVER_CACHE_PATTERNS.some(function (pattern) {
    return pattern.test(url);
  });
}

/**
 * Determine if a request is for a static asset.
 * @param {Request} request
 * @returns {boolean}
 */
function isStaticAsset(request) {
  var url = request.url;
  return /\.(js|css|png|jpg|jpeg|gif|svg|ico|woff|woff2|ttf|eot|webp|avif)(\?.*)?$/i.test(url);
}

/**
 * Determine if a request is an API call.
 * @param {Request} request
 * @returns {boolean}
 */
function isApiRequest(request) {
  var url = new URL(request.url);
  var path = url.pathname;
  return path.startsWith('/api/') || path.startsWith('/method/');
}

/**
 * Determine if a request is for an HTML page.
 * @param {Request} request
 * @returns {boolean}
 */
function isHtmlRequest(request) {
  var accept = request.headers.get('Accept') || '';
  return request.mode === 'navigate' || accept.includes('text/html');
}

// ---------------------------------------------------------------------------
// Install Event - Pre-cache APP_SHELL_ASSETS
// ---------------------------------------------------------------------------
self.addEventListener('install', function (event) {
  event.waitUntil(
    caches.open(STATIC_CACHE).then(function (cache) {
      return cache.addAll(APP_SHELL_ASSETS);
    }).then(function () {
      return self.skipWaiting();
    })
  );
});

// ---------------------------------------------------------------------------
// Activate Event - Clean up old caches
// ---------------------------------------------------------------------------
self.addEventListener('activate', function (event) {
  var validCaches = [STATIC_CACHE, API_CACHE, HTML_CACHE];

  event.waitUntil(
    caches.keys().then(function (cacheNames) {
      return Promise.all(
        cacheNames
          .filter(function (name) {
            return name.startsWith('tradehub-') && validCaches.indexOf(name) === -1;
          })
          .map(function (name) {
            return caches.delete(name);
          })
      );
    }).then(function () {
      return self.clients.claim();
    })
  );
});

// ---------------------------------------------------------------------------
// Fetch Event - Route requests to the appropriate caching strategy
// ---------------------------------------------------------------------------
self.addEventListener('fetch', function (event) {
  var request = event.request;

  // Only handle GET requests
  if (request.method !== 'GET') {
    return;
  }

  // Never cache sensitive endpoints
  if (shouldNeverCache(request.url)) {
    return;
  }

  // Strategy 1: Cache-First for static assets
  if (isStaticAsset(request)) {
    event.respondWith(cacheFirst(request, STATIC_CACHE));
    return;
  }

  // Strategy 2: Network-First for API calls
  if (isApiRequest(request)) {
    event.respondWith(networkFirst(request, API_CACHE));
    return;
  }

  // Strategy 3: Stale-While-Revalidate for HTML pages
  if (isHtmlRequest(request)) {
    event.respondWith(staleWhileRevalidate(request, HTML_CACHE));
    return;
  }
});

// ---------------------------------------------------------------------------
// Caching Strategies
// ---------------------------------------------------------------------------

/**
 * Cache-First strategy.
 * Serves from cache if available, otherwise fetches from network and caches.
 * Falls back to offline page on failure.
 *
 * @param {Request} request
 * @param {string} cacheName
 * @returns {Promise<Response>}
 */
function cacheFirst(request, cacheName) {
  return caches.match(request).then(function (cached) {
    if (cached) {
      return cached;
    }
    return fetch(request).then(function (response) {
      if (response && response.ok) {
        var clone = response.clone();
        caches.open(cacheName).then(function (cache) {
          cache.put(request, clone);
        });
      }
      return response;
    });
  }).catch(function () {
    return caches.match('/offline.html');
  });
}

/**
 * Network-First strategy.
 * Tries network first; on failure, serves from cache.
 * Successful responses are cached for future offline use.
 *
 * @param {Request} request
 * @param {string} cacheName
 * @returns {Promise<Response>}
 */
function networkFirst(request, cacheName) {
  return fetch(request).then(function (response) {
    if (response && response.ok) {
      var clone = response.clone();
      caches.open(cacheName).then(function (cache) {
        cache.put(request, clone);
      });
    }
    return response;
  }).catch(function () {
    return caches.match(request).then(function (cached) {
      return cached || caches.match('/offline.html');
    });
  });
}

/**
 * Stale-While-Revalidate strategy.
 * Serves from cache immediately while fetching a fresh copy in the background.
 * Falls back to offline page when both cache and network are unavailable.
 *
 * @param {Request} request
 * @param {string} cacheName
 * @returns {Promise<Response>}
 */
function staleWhileRevalidate(request, cacheName) {
  return caches.open(cacheName).then(function (cache) {
    return cache.match(request).then(function (cached) {
      var fetchPromise = fetch(request).then(function (response) {
        if (response && response.ok) {
          cache.put(request, response.clone());
        }
        return response;
      }).catch(function () {
        return null;
      });

      return cached || fetchPromise.then(function (response) {
        return response || caches.match('/offline.html');
      });
    });
  });
}
