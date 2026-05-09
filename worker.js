/**
 * Cloudflare Worker
 * - /api/stats?slug=...      → GET  { likes, dislikes }
 * - /api/vote                → POST { slug, action, title?, thumbnail?, category? }
 *                              action: like | unlike | dislike | undislike
 * - /api/popular?limit=10    → GET  [{ slug, title, thumbnail, category, likes }]
 * - 나머지 경로              → 정적 에셋 (public/)
 */

const CORS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type",
};

function json(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json; charset=utf-8", ...CORS },
  });
}

async function getStats(env, slug) {
  const raw = await env.LIKES.get(`post:${slug}`);
  if (!raw) return { likes: 0, dislikes: 0 };
  try { return JSON.parse(raw); } catch { return { likes: 0, dislikes: 0 }; }
}

async function updatePopular(env, slug, stats, meta) {
  const raw = await env.LIKES.get("popular:index");
  let idx = [];
  if (raw) { try { idx = JSON.parse(raw); } catch {} }

  const i = idx.findIndex((x) => x.slug === slug);
  const entry = {
    slug,
    title: meta.title || (i >= 0 ? idx[i].title : slug),
    thumbnail: meta.thumbnail || (i >= 0 ? idx[i].thumbnail : ""),
    category: meta.category || (i >= 0 ? idx[i].category : ""),
    likes: stats.likes,
    dislikes: stats.dislikes,
  };

  if (i >= 0) idx[i] = entry; else idx.push(entry);
  idx.sort((a, b) => (b.likes || 0) - (a.likes || 0));
  idx = idx.slice(0, 50);

  await env.LIKES.put("popular:index", JSON.stringify(idx));
}

async function handleApi(url, request, env) {
  if (request.method === "OPTIONS") {
    return new Response(null, { headers: CORS });
  }

  // GET /api/stats
  if (url.pathname === "/api/stats" && request.method === "GET") {
    const slug = url.searchParams.get("slug");
    if (!slug) return json({ error: "slug required" }, 400);
    return json(await getStats(env, slug));
  }

  // POST /api/vote
  if (url.pathname === "/api/vote" && request.method === "POST") {
    let body;
    try { body = await request.json(); }
    catch { return json({ error: "invalid json" }, 400); }

    const { slug, action, title, thumbnail, category } = body || {};
    if (!slug || !action) return json({ error: "slug and action required" }, 400);

    const stats = await getStats(env, slug);

    switch (action) {
      case "like":       stats.likes += 1; break;
      case "unlike":     stats.likes = Math.max(0, stats.likes - 1); break;
      case "dislike":    stats.dislikes += 1; break;
      case "undislike":  stats.dislikes = Math.max(0, stats.dislikes - 1); break;
      default: return json({ error: "invalid action" }, 400);
    }

    await env.LIKES.put(`post:${slug}`, JSON.stringify(stats));
    await updatePopular(env, slug, stats, { title, thumbnail, category });
    return json(stats);
  }

  // GET /api/popular
  if (url.pathname === "/api/popular" && request.method === "GET") {
    const limit = parseInt(url.searchParams.get("limit") || "10", 10);
    const raw = await env.LIKES.get("popular:index");
    let idx = [];
    if (raw) { try { idx = JSON.parse(raw); } catch {} }
    // 좋아요 1 이상인 글만 노출
    idx = idx.filter((x) => (x.likes || 0) > 0).slice(0, limit);
    return json(idx);
  }

  return json({ error: "not found" }, 404);
}

async function fetchAssetWithFallback(request, env) {
  // 1차: 원본 요청 그대로
  let res = await env.ASSETS.fetch(request);
  if (res.status !== 404) return res;

  // 2차: 퍼센트 디코드 + NFC 정규화 후 재시도
  // (한글 파일명이 NFC/NFD 불일치로 매칭 안 되는 경우 대비)
  try {
    const url = new URL(request.url);
    const decoded = decodeURIComponent(url.pathname).normalize("NFC");
    const encoded = encodeURI(decoded);
    if (encoded !== url.pathname) {
      const newUrl = new URL(encoded + url.search, url.origin);
      const retry = await env.ASSETS.fetch(new Request(newUrl.toString(), request));
      if (retry.status !== 404) return retry;
    }
    // 3차: NFD 정규화 재시도
    const nfd = decodeURIComponent(url.pathname).normalize("NFD");
    const nfdEncoded = encodeURI(nfd);
    if (nfdEncoded !== url.pathname) {
      const newUrl2 = new URL(nfdEncoded + url.search, url.origin);
      const retry2 = await env.ASSETS.fetch(new Request(newUrl2.toString(), request));
      if (retry2.status !== 404) return retry2;
    }
  } catch (_) {}

  return res;
}

function withNoCacheHeaders(res) {
  // HTML 응답은 엣지/브라우저 캐시 금지 (새 배포 즉시 반영)
  const contentType = res.headers.get("content-type") || "";
  if (!contentType.includes("text/html")) return res;

  const newHeaders = new Headers(res.headers);
  newHeaders.set("Cache-Control", "public, max-age=0, s-maxage=0, must-revalidate");
  newHeaders.set("CDN-Cache-Control", "no-store");
  newHeaders.set("Cloudflare-CDN-Cache-Control", "no-store");
  return new Response(res.body, {
    status: res.status,
    statusText: res.statusText,
    headers: newHeaders,
  });
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname.startsWith("/api/")) {
      return handleApi(url, request, env);
    }
    const res = await fetchAssetWithFallback(request, env);
    return withNoCacheHeaders(res);
  },
};
