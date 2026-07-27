const express = require("express");
const { Pool } = require("pg");
const app = express();
const port = process.env.PORT || 8080;
const pool = new Pool({ connectionString: process.env.DATABASE_URL });
app.get("/health", (_req, res) => res.json({ ok: true }));
app.listen(port, () => console.log(`api listening on ${port}`));
module.exports = { app, pool };
