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
];
