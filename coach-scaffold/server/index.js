import express from "express";
import cors from "cors";
const app = express();
app.use(cors(), express.json());
app.get("/", (req, res) => res.send("Server is working"));
app.listen(3001, () => console.log("API on :3001"));
