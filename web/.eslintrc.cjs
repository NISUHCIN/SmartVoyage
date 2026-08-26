module.exports = {
  root: true,
  env: { browser: true, es2022: true, node: true },
  extends: ['plugin:vue/vue3-essential', 'eslint:recommended'],
  parserOptions: { ecmaVersion: 'latest', sourceType: 'module' },
  rules: {
    'vue/multi-word-component-names': 'off',
    'no-unused-vars': ['warn', { argsIgnorePattern: '^_' }],
    'no-constant-condition': ['error', { checkLoops: false }]
  }
}
