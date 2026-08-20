const http = require("http");
const fs = require("fs");
const path = require("path");

const root = __dirname;
const mime = {
  ".html": "text/html",
  ".css": "text/css",
  ".js": "application/javascript",
  ".png": "image/png",
  ".svg": "image/svg+xml",
  ".webp": "image/webp",
  ".woff2": "font/woff2",
  ".webm": "video/webm",
};

const server = http.createServer((req, res) => {
  let u = decodeURIComponent((req.url || "/").split("?")[0]);
  if (u === "/") u = "/index.html";
  const f = path.normalize(path.join(root, u.replace(/^\//, "")));
  if (!f.startsWith(root) || !fs.existsSync(f) || fs.statSync(f).isDirectory()) {
    res.writeHead(404);
    return res.end("404 " + u);
  }
  res.writeHead(200, { "Content-Type": mime[path.extname(f)] || "application/octet-stream" });
  fs.createReadStream(f).pipe(res);
});

server.listen(3456, "127.0.0.1", () => {
  console.log("listening http://127.0.0.1:3456");
});
