import baseConfig from "./cfg/eslint.config.base.js";

export default [
  ...baseConfig,
  {
    /*
     * YAML 1.1 booleans (`on`/`off`) survive only when quoted; prettier-yml
     * strips the quotes during fix. Leave this file alone.
     */
    ignores: ["comicbox/config_default.yaml"],
  },
  {
    // Vendored byte for byte from json-cbl-standard; keep it diffable.
    ignores: [
      "comicbox/schemas/json-cbl-v1.0.schema.json",
      "schemas/json-cbl-v1.0.schema.json",
    ],
  },
];
