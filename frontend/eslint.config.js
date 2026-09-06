// @ts-check
//
// ESLint configuration, matching the house style used in the other repositories.
//
// THE DIVISION OF LABOUR
// Prettier owns formatting: indentation, quotes, semicolons, trailing commas,
// line breaks. ESLint owns correctness: unused variables, unsafe types, things
// that are legal but wrong.
//
// Do not add stylistic rules here. They only fight Prettier and produce errors
// that disappear the next time anybody formats the file.

const eslint = require('@eslint/js');
const { defineConfig } = require('eslint/config');
const tseslint = require('typescript-eslint');
const angular = require('angular-eslint');

module.exports = defineConfig([
    {
        ignores: ['dist/**', '.angular/**', 'coverage/**', 'node_modules/**']
    },
    {
        files: ['**/*.ts'],
        extends: [
            eslint.configs.recommended,
            tseslint.configs.recommended,
            tseslint.configs.stylistic,
            angular.configs.tsRecommended
        ],
        processor: angular.processInlineTemplates,
        rules: {
            '@angular-eslint/directive-selector': [
                'error',
                { type: 'attribute', prefix: 'app', style: 'camelCase' }
            ],
            '@angular-eslint/component-selector': [
                'error',
                { type: 'element', prefix: 'app', style: 'kebab-case' }
            ],

            // --- House rules, matching chore-api ---

            // Every declared function says what it returns. `allowExpressions`
            // is the one adaptation for Angular: inline callbacks passed to
            // `computed`, `effect` and array methods appear constantly, and
            // annotating each one adds noise without adding information.
            '@typescript-eslint/explicit-function-return-type': [
                'warn',
                { allowExpressions: true, allowTypedFunctionExpressions: true }
            ],

            // `any` switches off the type checker exactly where a type would
            // have helped. Use `unknown` and narrow it.
            '@typescript-eslint/no-explicit-any': 'error',

            '@typescript-eslint/no-unused-vars': [
                'warn',
                { argsIgnorePattern: '^_', destructuredArrayIgnorePattern: '^_' }
            ],

            'no-undef': 'off',

            // `console.log` is for debugging and should not survive review.
            // Warnings and errors are legitimate output.
            'no-console': ['warn', { allow: ['warn', 'error', 'info'] }],

            'max-len': [
                'warn',
                { code: 120, ignoreUrls: true, ignoreStrings: true, ignoreTemplateLiterals: true }
            ]
        }
    },
    {
        files: ['**/*.html'],
        extends: [angular.configs.templateRecommended, angular.configs.templateAccessibility],
        rules: {}
    },
    {
        // Tests may use looser typing, and test callbacks need not declare
        // return types.
        files: ['**/*.spec.ts'],
        rules: {
            '@typescript-eslint/explicit-function-return-type': 'off',
            '@typescript-eslint/no-explicit-any': 'off'
        }
    }
]);
