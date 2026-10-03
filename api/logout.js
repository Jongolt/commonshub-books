module.exports = function logout(req, res) {
  res.statusCode = 302;
  res.setHeader(
    "Set-Cookie",
    "chb_session=; HttpOnly; Secure; Path=/; SameSite=Lax; Max-Age=0"
  );
  res.setHeader("Location", "/");
  res.end();
};
