import js from "@eslint/js";
import globals from "globals";
import pluginVue from "eslint-plugin-vue";
import { defineConfig, globalIgnores } from "eslint/config";

export default defineConfig([
  globalIgnores(["dist/**", "e2e/artifacts/**", "e2e/*-snapshots/**"]),
  { files: ["**/*.{js,mjs,cjs,vue}"], plugins: { js }, extends: ["js/recommended"], languageOptions: { globals: globals.browser } },
  { files: ["*.config.js"], languageOptions: { globals: globals.node } },
  pluginVue.configs["flat/essential"],
]);
