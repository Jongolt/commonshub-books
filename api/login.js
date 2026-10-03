const { readSession, checkPassword, sessionCookie } = require("./auth");

function readBody(req) {
  if (req.body && typeof req.body === "object") return Promise.resolve(req.body);
  if (typeof req.body === "string") {
    try {
      return Promise.resolve(JSON.parse(req.body));
    } catch (err) {
      return Promise.resolve({});
    }
  }
  return new Promise((resolve) => {
    const chunks = [];
    let size = 0;
    req.on("data", (chunk) => {
      size += chunk.length;
      if (size > 2048) {
        req.destroy();
        resolve({});
        return;
      }
      chunks.push(chunk);
    });
    req.on("end", () => {
      try {
        resolve(JSON.parse(Buffer.concat(chunks).toString() || "{}"));
      } catch (err) {
        resolve({});
      }
    });
  });
}

module.exports = async function login(req, res) {
  if (req.method === "GET") {
    res.statusCode = readSession(req) ? 204 : 401;
    res.end();
    return;
  }
  if (req.method !== "POST") {
    res.statusCode = 405;
    res.end();
    return;
  }
  const data = await readBody(req);
  if (!checkPassword(data.username, data.password)) {
    res.statusCode = 401;
    res.setHeader("Content-Type", "application/json");
    res.end(JSON.stringify({ ok: false }));
    return;
  }
  res.statusCode = 200;
  const secure = process.env.VERCEL === "1" || req.headers["x-forwarded-proto"] === "https";
  res.setHeader("Set-Cookie", sessionCookie(process.env.SITE_USER, secure));
  res.setHeader("Content-Type", "application/json");
  res.end(JSON.stringify({ ok: true }));
};
