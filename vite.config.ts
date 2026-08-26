import { defineConfig } from "vite";

export default defineConfig({
  root: "monster_builder/web",
  build: {
    outDir: "dist",
    emptyOutDir: true,
  },
});
