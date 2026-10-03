module.exports = function logout(req, res) {
  const secure = process.env.VERCEL === "1" || req.headers["x-forwarded-proto"] === "https";
  const locked = secure ? "; Secure" : "";
  res.statusCode = 302;
  res.setHeader(
    "Set-Cookie",
    `chb_session=; HttpOnly${locked}; Path=/; SameSite=Lax; Max-Age=0`
  );
  res.setHeader("Location", "/");
  res.end();
};
