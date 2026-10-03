const crypto = require("crypto");

function secret() {
  return process.env.AUTH_SECRET || "";
}

function cookie(req, name) {
  const header = req.headers.cookie || "";
  for (const part of header.split(";")) {
    const [key, ...rest] = part.trim().split("=");
    if (key === name) return decodeURIComponent(rest.join("="));
  }
  return "";
}

function safeEqual(left, right) {
  const a = crypto.createHash("sha256").update(String(left), "utf8").digest();
  const b = crypto.createHash("sha256").update(String(right), "utf8").digest();
  return crypto.timingSafeEqual(a, b);
}

function checkPassword(username, password) {
  const user = process.env.SITE_USER || "";
  const pass = process.env.SITE_PASSWORD || "";
  if (!user || !pass || !secret()) return false;
  return safeEqual(username || "", user) && safeEqual(password || "", pass);
}

function sign(payload) {
  const key = secret();
  if (!key) return "";
  const body = Buffer.from(JSON.stringify(payload)).toString("base64url");
  const sig = crypto.createHmac("sha256", key).update(body).digest("base64url");
  return `${body}.${sig}`;
}

function readSession(req) {
  const key = secret();
  if (!key) return null;
  const raw = cookie(req, "chb_session");
  const dot = raw.lastIndexOf(".");
  if (dot <= 0) return null;
  const body = raw.slice(0, dot);
  const sig = raw.slice(dot + 1);
  const expected = crypto.createHmac("sha256", key).update(body).digest("base64url");
  if (!safeEqual(sig, expected)) return null;
  let payload;
  try {
    payload = JSON.parse(Buffer.from(body, "base64url").toString());
  } catch (err) {
    return null;
  }
  if (!payload || payload.exp < Date.now()) return null;
  if (payload.u !== process.env.SITE_USER) return null;
  return payload;
}

function sessionCookie(username, secure) {
  const token = sign({ u: username, exp: Date.now() + 12 * 60 * 60 * 1000 });
  const locked = secure ? "; Secure" : "";
  return `chb_session=${token}; HttpOnly${locked}; Path=/; SameSite=Lax; Max-Age=43200`;
}

function notFound(req, res) {
  res.statusCode = 404;
  res.end();
}

notFound.readSession = readSession;
notFound.checkPassword = checkPassword;
notFound.sessionCookie = sessionCookie;
module.exports = notFound;
