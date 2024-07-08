import { FlatCompat } from "@eslint/eslintrc";
import js from "@eslint/js";
import eslintConfigPrettier from "eslint-config-prettier";
import eslintPluginArrayFunc from "eslint-plugin-array-func";
import eslintPluginJsonc from "eslint-plugin-jsonc";
import eslintPluginMarkdown from "eslint-plugin-markdown";
import eslintPluginNoSecrets from "eslint-plugin-no-secrets";
// import eslintPluginNoUnsanitized from "eslint-plugin-no-unsanitized";
// import eslintPluginNoUseExtendNative from "eslint-plugin-no-use-extend-native";
import eslintPluginPrettier from "eslint-plugin-prettier";
import eslintPluginPrettierRecommended from "eslint-plugin-prettier/recommended";
import eslintPluginPromise from "eslint-plugin-promise";
import eslintPluginRegexp from "eslint-plugin-regexp";
import eslintPluginSecurity from "eslint-plugin-security";
import eslintPluginSimpleImportSort from "eslint-plugin-simple-import-sort";
import eslintPluginSonarjs from "eslint-plugin-sonarjs";
import eslintPluginToml from "eslint-plugin-toml";
import eslintPluginUnicorn from "eslint-plugin-unicorn";
import eslintPluginYml from "eslint-plugin-yml";
import globals from "globals";

const compat = new FlatCompat();

const IGNORES = [
  "!.circleci",
  "**/__pycache__",
  "**/*min.css",
  "**/*min.js",
  "*~",
  ".git",
  ".mypy_cache",
  ".pytest_cache",
  ".ruff_cache",
  ".venv",
  "dist",
  "node_modules",
  "package-lock.json",
  "poetry.lock",
  "test-results",
  "typings",
];
Object.freeze(IGNORES);
const FLAT_RECOMMENDED = "flat/recommended";
Object.freeze(FLAT_RECOMMENDED);

export default [
  js.configs.recommended,
  eslintPluginArrayFunc.configs.all,
  ...eslintPluginJsonc.configs["flat/recommended-with-jsonc"],
  ...eslintPluginMarkdown.configs.recommended,
  // eslintPluginNoUseExtendNative.configs.recommended,
  // eslintPluginNoUnsanitized.configs.recommended,
  eslintPluginPrettierRecommended,
  eslintPluginPromise.configs[FLAT_RECOMMENDED],
  eslintPluginRegexp.configs[FLAT_RECOMMENDED],
  eslintPluginSecurity.configs.recommended,
  eslintPluginSonarjs.configs.recommended,
  ...eslintPluginToml.configs[FLAT_RECOMMENDED],
  ...eslintPluginYml.configs["flat/standard"],
  ...eslintPluginYml.configs["flat/prettier"],
  eslintConfigPrettier, // Best if last
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
      arrayFunc: eslintPluginArrayFunc,
      jsonc: eslintPluginJsonc,
      markdown: eslintPluginMarkdown,
      "no-secrets": eslintPluginNoSecrets,
      // "no-use-extend-native": eslintPluginNoUseExtendNative,
      // "no-unsantized": eslintPluginNoUnsanitized,
      prettier: eslintPluginPrettier,
      promise: eslintPluginPromise,
      security: eslintPluginSecurity,
      "simple-import-sort": eslintPluginSimpleImportSort,
      // sonarjs: eslintPluginSonarjs,
      toml: eslintPluginToml,
      unicorn: eslintPluginUnicorn,
      yml: eslintPluginYml,
    },
    rules: {
      "array-func/prefer-array-from": "off", // for modern browsers the spread operator, as preferred by unicorn, works fine.
      "max-params": ["warn", 4],
      "no-console": "warn",
      "no-debugger": "warn",
      "no-constructor-bind/no-constructor-bind": "error",
      "no-constructor-bind/no-constructor-state": "error",
      "no-secrets/no-secrets": "error",
      "prettier/prettier": "warn",
      "security/detect-object-injection": "off",
      "simple-import-sort/exports": "warn",
      "simple-import-sort/imports": "warn",
      "space-before-function-paren": "off",
      "unicorn/switch-case-braces": ["warn", "avoid"],
      "unicorn/prefer-node-protocol": "off",
      "unicorn/prevent-abbreviations": "off",
      "unicorn/filename-case": [
        "error",
        { case: "kebabCase", ignore: [".*.md", "config_default.yaml"] },
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
    ignores: IGNORES,
  },
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
  {
    files: ["**/*.md/*.sh"],
    rules: {
      "prettier/prettier": ["error", { parser: "sh" }],
    },
  },
  {
    files: ["**/*.toml"],
    rules: {
      "prettier/prettier": ["error", { parser: "toml" }],
    },
  },
  {
    files: ["docker-compose*.yaml"],
    rules: {
      "yml/no-empty-mapping-value": "off",
    },
  },
  {
    files: ["tests/**/*.json"],
    rules: {
      "no-secrets/no-secrets": "off",
    },
  },
  ...compat.config({
    root: true,
    env: {
      es2024: true,
      node: true,
    },
    extends: [
      // PRACTICES
      // "plugin:import/recommended",
    ],
    parserOptions: {
      ecmaFeatures: {
        impliedStrict: true,
      },
      ecmaVersion: "latest",
    },
    plugins: [
      // "import", // https://github.com/import-js/eslint-plugin-import/issues/2556
      "no-constructor-bind", // https://github.com/markalfred/eslint-plugin-no-constructor-bind
    ],
    rules: {
      "no-constructor-bind/no-constructor-bind": "error",
      "no-constructor-bind/no-constructor-state": "error",
    },
    ignorePatterns: IGNORES,
  }),
];
