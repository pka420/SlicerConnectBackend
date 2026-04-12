import express from "express";
import cors from "cors";
import dotenv from "dotenv";
import path from "path";
import fs from "fs";
import { fileURLToPath } from "url";

dotenv.config();
const app = express();
app.use(cors());
app.use(express.json());

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

app.use(express.static(path.join(__dirname, "src")));

app.get("/", (req, res) => {
    res.sendFile(path.join(__dirname, "src", "index.html"));
});

app.get("/verify", (req, res) => {
    const html = fs.readFileSync(path.join(__dirname, "src", "verify.html"), "utf8");
    const injected = html.replace("__FRONTEND_URL__", process.env.FRONTEND_URL || "");
    res.send(injected);
});

app.get("/verify", (req, res) => {
    const html = fs.readFileSync(path.join(__dirname, "src", "verify.html"), "utf8");
    const injected = html.replace("__FRONTEND_URL__", process.env.FRONTEND_URL || "");
    res.send(injected);
});

app.get("/docs", (req, res) => {
    res.sendFile(path.join(__dirname, "src", "docs.html"));
});

const PORT = process.env.PORT || 3000;
app.listen(PORT, () => {
    console.log(`Server running on port ${PORT}`);
});
