const fs = require("node:fs");
const http = require("node:http");
const path = require("node:path");
const { URL } = require("node:url");

const MIME_TYPES = {
  ".css": "text/css; charset=utf-8",
  ".gif": "image/gif",
  ".html": "text/html; charset=utf-8",
  ".ico": "image/x-icon",
  ".js": "text/javascript; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".map": "application/json; charset=utf-8",
  ".mjs": "text/javascript; charset=utf-8",
  ".png": "image/png",
  ".svg": "image/svg+xml",
  ".wasm": "application/wasm",
  ".webp": "image/webp",
  ".woff": "font/woff",
  ".woff2": "font/woff2"
};

function sendNotFound(response) {
  response.writeHead(404, { "Content-Type": "text/plain; charset=utf-8" });
  response.end("Not found");
}

function sendFile(response, filePath) {
  const extension = path.extname(filePath).toLowerCase();
  response.writeHead(200, {
    "Cache-Control": extension === ".html" ? "no-store" : "public, max-age=31536000",
    "Content-Type": MIME_TYPES[extension] || "application/octet-stream"
  });
  fs.createReadStream(filePath).pipe(response);
}

function proxyToBackend(request, response, backendPort) {
  const proxy = http.request(
    {
      hostname: "127.0.0.1",
      port: backendPort,
      path: request.url,
      method: request.method,
      headers: {
        ...request.headers,
        host: `127.0.0.1:${backendPort}`
      }
    },
    (backendResponse) => {
      response.writeHead(
        backendResponse.statusCode || 502,
        backendResponse.headers
      );
      backendResponse.pipe(response);
    }
  );

  proxy.on("error", (error) => {
    response.writeHead(502, { "Content-Type": "application/json" });
    response.end(JSON.stringify({ detail: error.message }));
  });

  request.pipe(proxy);
}

function resolveStaticPath(rootDir, requestUrl) {
  const url = new URL(requestUrl || "/", "http://127.0.0.1");
  let pathname = "/";
  try {
    pathname = decodeURIComponent(url.pathname);
  } catch {
    return null;
  }
  const requested = pathname === "/" ? "/index.html" : pathname;
  const candidate = path.resolve(rootDir, `.${requested}`);
  const root = path.resolve(rootDir);

  if (candidate !== root && !candidate.startsWith(root + path.sep)) {
    return null;
  }
  return candidate;
}

function createDesktopServer({ distDir, backendPort, port = 0 }) {
  if (!fs.existsSync(path.join(distDir, "index.html"))) {
    throw new Error(`Frontend bundle not found: ${distDir}`);
  }

  const server = http.createServer((request, response) => {
    if ((request.url || "").startsWith("/api/")) {
      proxyToBackend(request, response, backendPort);
      return;
    }

    const candidate = resolveStaticPath(distDir, request.url);
    if (!candidate) {
      sendNotFound(response);
      return;
    }

    fs.stat(candidate, (error, stat) => {
      if (!error && stat.isFile()) {
        sendFile(response, candidate);
        return;
      }

      const indexPath = path.join(distDir, "index.html");
      sendFile(response, indexPath);
    });
  });

  return new Promise((resolve, reject) => {
    server.once("error", reject);
    server.listen(port, "127.0.0.1", () => {
      server.off("error", reject);
      const address = server.address();
      if (!address || typeof address === "string") {
        reject(new Error("Could not allocate desktop server port."));
        return;
      }
      resolve({
        close: () => server.close(),
        port: address.port,
        url: `http://127.0.0.1:${address.port}`
      });
    });
  });
}

module.exports = {
  createDesktopServer,
  resolveStaticPath
};
