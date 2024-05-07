import { FlatCompat } from "@eslint/eslintrc";
import js from "@eslint/js";
import arrayFunc from "eslint-plugin-array-func";
// import plugin broken for flag config
// https://github.com/import-js/eslint-plugin-import/issues/2556
// import importPlugin from "eslint-plugin-import";
import eslintPluginJsonc from "eslint-plugin-jsonc";
import markdown from "eslint-plugin-markdown";
import prettier from "eslint-plugin-prettier";
import eslintPluginPrettierRecommended from "eslint-plugin-prettier/recommended";
import eslintPluginSecurity from "eslint-plugin-security";
import simpleImportSort from "eslint-plugin-simple-import-sort";
import sonarjs from "eslint-plugin-sonarjs";
import eslintPluginToml from "eslint-plugin-toml";
import unicorn from "eslint-plugin-unicorn";
import eslintPluginYml from "eslint-plugin-yml";
import globals from "globals";

const compat = new FlatCompat();

export default [
  {
    languageOptions: {
      globals: {
        ...globals.node,
      },
    },
    linterOptions: {
      reportUnusedDisableDirectives: "warn",
    },
    plugins: {
      arrayFunc,
      // import: importPlugin,
      markdown,
      prettier,
      security: eslintPluginSecurity,
      //sonarjs,
      "simple-import-sort": simpleImportSort,
      toml: eslintPluginToml,
      unicorn,
      yml: eslintPluginYml,
    },
    rules: {
      "array-func/prefer-array-from": "off", // for modern browsers the spread operator, as preferred by unicorn, works fine.
      "max-params": ["warn", 4],
      "no-console": "warn",
      "no-debugger": "warn",
      "no-constructor-bind/no-constructor-bind": "error",
      "no-constructor-bind/no-constructor-state": "error",
      "prettier/prettier": "warn",
      "security/detect-object-injection": "off",
      "simple-import-sort/imports": "warn",
      "simple-import-sort/exports": "warn",
      "space-before-function-paren": "off",
      "unicorn/switch-case-braces": ["warn", "avoid"],
      "unicorn/prefer-node-protocol": 0,
      "unicorn/prevent-abbreviations": "off",
      "unicorn/filename-case": [
        "error",
        { case: "kebabCase", ignore: [".*.md", ".*.yaml"] },
      ],
      /*
     ...importPlugin.configs["recommended"].rules,
     "import/no-unresolved": [
       "error",
       {
         ignore: ["^[@]"],
       },
     ],
     */
    },
    /*
    settings: {
      "import/parsers": {
        espree: [".js", ".cjs", ".mjs", ".jsx"],
        "@typescript-eslint/parser": [".ts"],
      },
      "import/resolver": {
        typescript: true, 
        node: true,
      },
    },
     */
  },
  js.configs.recommended,
  arrayFunc.configs.all,
  ...eslintPluginJsonc.configs["flat/recommended-with-jsonc"],
  ...markdown.configs.recommended,
  eslintPluginPrettierRecommended,
  eslintPluginSecurity.configs.recommended,
  sonarjs.configs.recommended,
  ...eslintPluginToml.configs["flat/recommended"],
  ...eslintPluginYml.configs["flat/standard"],
  ...eslintPluginYml.configs["flat/prettier"],
  {
    files: ["**/*.md"],
    processor: "markdown/markdown",
    rules: {
      "prettier/prettier": ["warn", { parser: "markdown" }],
    },
  },
  {
    files: ["**/*.md/*.js"], // Will match js code inside *.md files
    rules: {
      "no-unused-vars": "off",
      "no-undef": "off",
    },
  },
  ...compat.config({
    root: true,
    env: {
      browser: true,
      es2024: true,
      node: true,
    },
    extends: [
      // PRACTICES
      "plugin:eslint-comments/recommended",
      // "plugin:import/recommended",
      "plugin:no-use-extend-native/recommended",
      "plugin:optimize-regex/all",
      "plugin:promise/recommended",
      "plugin:switch-case/recommended",
      // SECURITY
      "plugin:no-unsanitized/DOM",
    ],
    overrides: [
      {
        files: ["tests/test_files/**/mupdf.json"],
        rules: {
          "no-secrets/no-secrets": "off",
        },
      },
    ],
    parserOptions: {
      ecmaFeatures: {
        impliedStrict: true,
      },
      ecmaVersion: "latest",
    },
    plugins: [
      "eslint-comments",
      //"import",
      "no-constructor-bind",
      "no-secrets",
      "no-unsanitized",
      "no-use-extend-native",
      "optimize-regex",
      "promise",
      "switch-case",
    ],
    rules: {
      "no-constructor-bind/no-constructor-bind": "error",
      "no-constructor-bind/no-constructor-state": "error",
      "no-secrets/no-secrets": "error",
      "eslint-comments/no-unused-disable": 1,
      "switch-case/newline-between-switch-case": "off", // Malfunctioning
    },
    ignorePatterns: [
      "*~",
      "**/__pycache__",
      ".git",
      "!.circleci",
      ".mypy_cache",
      ".ruff_cache",
      ".pytest_cache",
      ".venv*",
      "dist",
      "node_modules",
      "package-lock.json",
      "poetry.lock",
      "test-results",
      "typings",
    ],
  }),
];
