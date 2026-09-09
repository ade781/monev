/**
 * CLOUDFLARE WORKER REVERSE PROXY FOR KEMNAKER MONEV
 * Script ini bertindak sebagai jembatan (reverse proxy) dari server cloud (Vercel)
 * ke server Kemnaker (maganghub.kemnaker.go.id, account.kemnaker.go.id, monev-api).
 * 
 * Cara Penggunaan:
 * 1. Buka dash.cloudflare.com -> Workers & Pages -> Create Worker
 * 2. Beri nama (misal: monev-proxy) lalu klik Deploy.
 * 3. Klik Edit Code, paste isi file ini, lalu klik Deploy.
 * 4. Salin URL Worker Anda (misal: https://monev-proxy.user.workers.dev)
 * 5. Pasang URL tersebut ke Vercel Environment Variables:
 *    CLOUDFLARE_WORKER_URL=https://monev-proxy.user.workers.dev
 */

export default {
  async fetch(request, env, ctx) {
    // Handle CORS preflight
    if (request.method === "OPTIONS") {
      return new Response(null, {
        headers: {
          "Access-Control-Allow-Origin": "*",
          "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS",
          "Access-Control-Allow-Headers": "*",
        },
      });
    }

    const currentUrl = new URL(request.url);
    const targetUrlStr = currentUrl.searchParams.get("url");

    if (!targetUrlStr) {
      return new Response(JSON.stringify({
        status: "online",
        message: "Monev Cloudflare Reverse Proxy aktif!",
        usage: "/?url=https://maganghub.kemnaker.go.id/..."
      }, null, 2), {
        status: 200,
        headers: { "Content-Type": "application/json" }
      });
    }

    let targetUrl;
    try {
      targetUrl = new URL(targetUrlStr);
    } catch (e) {
      return new Response(JSON.stringify({ error: "Invalid target URL: " + targetUrlStr }), {
        status: 400,
        headers: { "Content-Type": "application/json" }
      });
    }

    // Salin dan sesuaikan headers
    const newHeaders = new Headers();
    for (const [key, value] of request.headers.entries()) {
      // Abaikan header host asli agar target menerima Host sesuai domainnya
      if (!["host", "cf-connecting-ip", "cf-ray", "cf-visitor"].includes(key.toLowerCase())) {
        newHeaders.set(key, value);
      }
    }
    newHeaders.set("Host", targetUrl.host);

    // Forward request ke target Kemnaker
    try {
      const response = await fetch(targetUrl.toString(), {
        method: request.method,
        headers: newHeaders,
        body: ["GET", "HEAD"].includes(request.method) ? undefined : await request.arrayBuffer(),
        redirect: "manual" // Penting: Jangan auto-follow redirect agar cookie dan set-cookie tidak hilang
      });

      const responseHeaders = new Headers();
      
      // Salin response headers
      for (const [key, value] of response.headers.entries()) {
        if (key.toLowerCase() === "set-cookie") {
          // Bersihkan atribut Domain agar cookie diterima oleh client
          const cleanedCookie = value.replace(/;\s*domain=[^;]+/gi, "");
          responseHeaders.append("Set-Cookie", cleanedCookie);
        } else if (key.toLowerCase() === "location") {
          // Jika ada redirect, arahkan balik lewat worker
          let redirectTarget = value;
          if (redirectTarget.startsWith("/")) {
            redirectTarget = `${targetUrl.protocol}//${targetUrl.host}${redirectTarget}`;
          }
          const wrappedRedirect = `${currentUrl.origin}/?url=${encodeURIComponent(redirectTarget)}`;
          responseHeaders.set("Location", wrappedRedirect);
        } else {
          responseHeaders.set(key, value);
        }
      }

      responseHeaders.set("Access-Control-Allow-Origin", "*");

      return new Response(response.body, {
        status: response.status,
        statusText: response.statusText,
        headers: responseHeaders
      });

    } catch (err) {
      return new Response(JSON.stringify({
        error: "Gagal menghubungkan ke target Kemnaker",
        detail: err.message
      }), {
        status: 502,
        headers: { "Content-Type": "application/json" }
      });
    }
  },

  /**
   * CRON TRIGGER SCHEDULER (100% TEPAT WAKTU PER DETIK DI CLOUDFLARE EDGE)
   * Jadwal 7 Hari:
   * - 0 12 * * * = 12:00 UTC (19:00 WIB) -> Pengingat Santai
   * - 0 13 * * * = 13:00 UTC (20:00 WIB) -> Pengingat Keras
   * - 0 14 * * * = 14:00 UTC (21:00 WIB) -> Auto Monev Cadangan
   */
  async scheduled(event, env, ctx) {
    const cron = event.cron;
    const now = new Date();
    const hourUtc = now.getUTCHours();
    const vercelHost = (env && env.VERCEL_DOMAIN) ? env.VERCEL_DOMAIN.replace(/\/+$/, "") : "https://monev-wine.vercel.app";
    const cronSecret = (env && env.CRON_SECRET) ? env.CRON_SECRET.trim() : "";

    let path = "";
    if (cron === "0 12 * * *" || hourUtc === 12) {
      path = "/api/cron?type=reminder&mode=santai";
    } else if (cron === "0 13 * * *" || hourUtc === 13) {
      path = "/api/cron?type=reminder&mode=keras";
    } else if (cron === "0 14 * * *" || hourUtc === 14) {
      path = "/api/cron?type=auto";
    } else {
      console.log(`[CF Cron Idle] Scheduled trigger pada jam ${hourUtc} UTC di luar jadwal (12, 13, 14 UTC). Tidak ada request yang dikirim.`);
      return;
    }

    if (cronSecret && path.includes("type=auto")) {
      path += `&secret=${encodeURIComponent(cronSecret)}`;
    }

    const targetEndpoint = `${vercelHost}${path}`;
    const reqHeaders = {
      "User-Agent": "Cloudflare-Worker-Cron/1.0"
    };
    if (cronSecret) {
      reqHeaders["Authorization"] = `Bearer ${cronSecret}`;
    }

    // Fungsi pemanggil dengan Timeout 55s dan Auto-Retry 2x jika terjadi kendala jaringan/cold start
    const executeScheduledTask = async () => {
      const maxRetries = 2;
      for (let attempt = 1; attempt <= maxRetries; attempt++) {
        const controller = new AbortController();
        const timer = setTimeout(() => controller.abort("Request Timeout 55s"), 55000);
        try {
          console.log(`[CF Cron Trigger] (Percobaan ${attempt}/${maxRetries}) Menghubungi: ${targetEndpoint}`);
          const res = await fetch(targetEndpoint, {
            method: "GET",
            headers: reqHeaders,
            signal: controller.signal
          });
          clearTimeout(timer);

          const body = await res.text();
          if (res.ok) {
            console.log(`[CF Cron Success] HTTP ${res.status}: ${body.slice(0, 200)}`);
            return;
          } else {
            console.warn(`[CF Cron Warning] HTTP ${res.status} pada percobaan ${attempt}: ${body.slice(0, 200)}`);
            if (attempt < maxRetries) {
              await new Promise(r => setTimeout(r, 3000)); // jeda 3 detik sebelum coba lagi
            }
          }
        } catch (err) {
          clearTimeout(timer);
          console.error(`[CF Cron Error] Gagal pada percobaan ${attempt}: ${err.name === "AbortError" ? "Timeout 55s" : err.message}`);
          if (attempt < maxRetries) {
            await new Promise(r => setTimeout(r, 3000));
          }
        }
      }
    };

    ctx.waitUntil(executeScheduledTask());
  }
};

